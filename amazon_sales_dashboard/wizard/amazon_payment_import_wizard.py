# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging
from datetime import datetime, date
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AmazonPaymentImportWizard(models.TransientModel):
    _name = 'amazon.payment.import.wizard'
    _description = 'Import Amazon Payment Excel / CSV File'

    state = fields.Selection([
        ('upload', 'Upload File'),
        ('result', 'Import Results & Log')
    ], default='upload', string="State")

    file_data = fields.Binary(string="Payment Excel / CSV / TSV File", required=True)
    filename = fields.Char(string="File Name")

    # Import Result Metrics
    import_batch_id = fields.Char(string="Batch Number", readonly=True)
    total_rows = fields.Integer(string="Total Rows Processed", readonly=True)
    imported_count = fields.Integer(string="Successfully Imported", readonly=True)
    duplicate_count = fields.Integer(string="Duplicates Skipped", readonly=True)
    log_details = fields.Text(string="Import Summary & Duplicate Log", readonly=True)

    def _parse_datetime(self, val_str):
        if not val_str or not str(val_str).strip():
            return False
        val_str = str(val_str).strip()
        formats = [
            '%Y-%m-%d %H:%M:%S %Z',
            '%Y-%m-%d %H:%M:%S',
            '%d-%m-%Y %H:%M:%S',
            '%d/%m/%Y %H:%M:%S',
            '%d.%m.%Y %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S%z',
            '%d-%m-%Y %H:%M',
            '%d/%m/%Y %H:%M',
            '%Y-%m-%d',
            '%d-%m-%Y',
            '%d/%m/%Y',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                continue
        # Fallback for ISO strings or timezone variations
        try:
            return datetime.fromisoformat(val_str)
        except Exception:
            pass
        _logger.warning(f"Could not parse payment datetime: {val_str}")
        return False

    def _parse_date(self, val_str):
        dt = self._parse_datetime(val_str)
        return dt.date() if dt else False

    def _parse_float(self, val_str):
        if not val_str or not str(val_str).strip():
            return 0.0
        try:
            return float(str(val_str).strip().replace(',', ''))
        except ValueError:
            return 0.0

    def _clean_str_id(self, val_str):
        if not val_str or not str(val_str).strip():
            return ''
        val_str = str(val_str).strip()
        if ('e+' in val_str.lower() or 'e-' in val_str.lower() or '.' in val_str):
            try:
                flt_val = float(val_str)
                if flt_val.is_integer():
                    return str(int(flt_val))
                return str(flt_val)
            except (ValueError, OverflowError):
                pass
        return val_str

    def _read_file_rows(self, file_bytes, filename=None):
        """
        Parses raw bytes of an uploaded file into a list of row lists.
        Supports Excel (.xlsx, .xls) via openpyxl / xlrd, and Text / CSV / TSV with auto-detected delimiter.
        """
        rows = []
        filename_lower = (filename or '').lower()
        is_excel = (
            filename_lower.endswith(('.xlsx', '.xls', '.xlsm')) or
            file_bytes.startswith(b'PK\x03\x04') or
            file_bytes.startswith(b'\xd0\xcf\x11\xe0')
        )

        def _format_cell(cell):
            if cell is None:
                return ''
            if isinstance(cell, datetime):
                return cell.strftime('%Y-%m-%d %H:%M:%S')
            if isinstance(cell, date):
                return cell.strftime('%Y-%m-%d')
            if isinstance(cell, float) and cell.is_integer():
                return str(int(cell))
            return str(cell).strip()

        if is_excel:
            # 1. Try openpyxl for .xlsx / .xlsm / PK files
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                sheet = wb.active
                for row in sheet.iter_rows(values_only=True):
                    if any(c is not None and str(c).strip() for c in row):
                        rows.append([_format_cell(c) for c in row])
            except Exception as ex_openpyxl:
                _logger.info(f"openpyxl parsing failed: {ex_openpyxl}")

            # 2. Try xlrd for legacy .xls if openpyxl didn't parse any rows
            if not rows:
                try:
                    import xlrd
                    wb = xlrd.open_workbook(file_contents=file_bytes)
                    sheet = wb.sheet_by_index(0)
                    for row_idx in range(sheet.nrows):
                        row = sheet.row_values(row_idx)
                        if any(c != '' and c is not None for c in row):
                            rows.append([_format_cell(c) for c in row])
                except Exception as ex_xlrd:
                    _logger.info(f"xlrd parsing failed: {ex_xlrd}")

        # 3. Fallback to Text / CSV / TSV decoding if Excel was not processed or returned no rows
        if not rows:
            text_content = False
            for encoding in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
                try:
                    if encoding in ('latin1', 'cp1252') and file_bytes.startswith(b'PK\x03\x04'):
                        continue
                    text_content = file_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

            if not text_content:
                raise UserError(_("Could not decode file encoding. Please ensure it is a valid text/CSV/Excel file."))

            lines = [l for l in text_content.splitlines() if l.strip()]
            if not lines:
                raise UserError(_("Uploaded file is empty."))

            first_line = lines[0]
            delimiter = '\t' if '\t' in first_line else (',' if ',' in first_line else ';')

            try:
                reader = csv.reader(lines, delimiter=delimiter)
                for row in reader:
                    if any(row):
                        rows.append([str(c).strip() for c in row])
            except Exception as ce:
                raise UserError(_("Could not parse file rows: %s") % ce)

        return rows

    def action_import(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("Please select a Payment Excel or CSV file to upload."))

        try:
            file_bytes = base64.b64decode(self.file_data)
        except Exception as e:
            raise UserError(_("Error decoding uploaded file: %s") % e)

        rows = self._read_file_rows(file_bytes, self.filename)

        if not rows or len(rows) < 2:
            raise UserError(_("Uploaded file does not contain valid data rows."))

        header = rows[0]
        data_rows = rows[1:]

        # Standardize header names (replace hyphens, spaces, slashes with underscores)
        header_map = {}
        for idx, col in enumerate(header):
            clean_col = str(col).strip().lower().replace('-', '_').replace(' ', '_').replace('/', '_')
            header_map[clean_col] = idx

        _logger.info(f"Importing Amazon Payment report with headers: {list(header_map.keys())}")

        # Check key payment headers
        if 'settlement_id' not in header_map and 'total_amount' not in header_map and 'amount' not in header_map:
            raise UserError(_("Invalid Amazon Payment File Header. Missing columns like 'settlement-id', 'amount', or 'total-amount'. Please upload a valid Amazon Payment Settlement report."))

        batch_id = fields.Datetime.now().strftime('PMT-BATCH-%Y%m%d-%H%M%S')
        PaymentRecord = self.env['amazon.payment.record']

        company_currency = self.env.company.currency_id
        
        total_rows = 0
        imported_count = 0
        duplicate_count = 0
        log_lines = []

        for row in data_rows:
            if not row or not any(row):
                continue

            total_rows += 1

            def get_val(key, is_id=False):
                idx = header_map.get(key)
                if idx is not None and idx < len(row):
                    val = str(row[idx]).strip()
                    if is_id and val:
                        return self._clean_str_id(val)
                    return val
                return ''

            settlement_id = get_val('settlement_id', is_id=True)
            order_id = get_val('order_id', is_id=True)
            amount_type = get_val('amount_type')
            amount_description = get_val('amount_description')
            amount = self._parse_float(get_val('amount'))
            posted_date_time = self._parse_datetime(get_val('posted_date_time')) or self._parse_datetime(get_val('posted_date'))
            order_item_code = get_val('order_item_code', is_id=True)

            # Duplicate check
            dup_domain = [
                ('settlement_id', '=', settlement_id),
                ('order_id', '=', order_id),
                ('amount_description', '=', amount_description),
                ('amount', '=', amount),
            ]
            if posted_date_time:
                dup_domain.append(('posted_date_time', '=', posted_date_time))
            if order_item_code:
                dup_domain.append(('order_item_code', '=', order_item_code))

            existing = PaymentRecord.search(dup_domain, limit=1)
            if existing:
                duplicate_count += 1
                log_lines.append(f"• [Dup Skipped] Settlement: {settlement_id} | Order ID: {order_id or 'N/A'} | Desc: {amount_description} | Amount: {amount}")
                continue

            try:
                # Currency Lookup
                curr_code = get_val('currency')
                currency = company_currency
                if curr_code:
                    found_curr = self.env['res.currency'].search([('name', '=ilike', curr_code)], limit=1)
                    if found_curr:
                        currency = found_curr

                vals = {
                    'import_batch_id': batch_id,
                    'settlement_id': settlement_id,
                    'settlement_start_date': self._parse_datetime(get_val('settlement_start_date')),
                    'settlement_end_date': self._parse_datetime(get_val('settlement_end_date')),
                    'deposit_date': self._parse_datetime(get_val('deposit_date')),
                    'total_amount': self._parse_float(get_val('total_amount')),
                    'currency_id': currency.id,
                    'currency_code': curr_code or currency.name,
                    'transaction_type': get_val('transaction_type'),
                    'order_id': order_id,
                    'merchant_order_id': get_val('merchant_order_id', is_id=True),
                    'adjustment_id': get_val('adjustment_id', is_id=True),
                    'shipment_id': get_val('shipment_id', is_id=True),
                    'marketplace_name': get_val('marketplace_name'),
                    'amount_type': amount_type,
                    'amount_description': amount_description,
                    'amount': amount,
                    'fulfillment_id': get_val('fulfillment_id', is_id=True),
                    'posted_date': self._parse_date(get_val('posted_date')) or (posted_date_time.date() if posted_date_time else False),
                    'posted_date_time': posted_date_time,
                    'order_item_code': order_item_code,
                    'merchant_order_item_id': get_val('merchant_order_item_id', is_id=True),
                    'merchant_adjustment_item_id': get_val('merchant_adjustment_item_id', is_id=True),
                    'sku': get_val('sku'),
                    'quantity_purchased': self._parse_float(get_val('quantity_purchased')),
                    'promotion_id': get_val('promotion_id'),
                    'state': 'draft',
                }

                PaymentRecord.create(vals)
                imported_count += 1
            except Exception as pe:
                _logger.warning(f"Error parsing payment row: {pe}")
                log_lines.append(f"• [PARSE ERROR] Settlement: {settlement_id} | Order ID: {order_id} | Error: {pe}")

        log_content = "\n".join(log_lines) if log_lines else "No duplicate records or errors encountered."

        self.write({
            'state': 'result',
            'import_batch_id': batch_id,
            'total_rows': total_rows,
            'imported_count': imported_count,
            'duplicate_count': duplicate_count,
            'log_details': log_content,
        })

        return {
            'name': _('Payment Import Results'),
            'type': 'ir.actions.act_window',
            'res_model': 'amazon.payment.import.wizard',
            'res_id': self.id,
            'views': [(False, 'form')],
            'view_mode': 'form',
            'target': 'new',
        }
