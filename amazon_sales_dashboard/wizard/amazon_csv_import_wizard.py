# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging
from datetime import datetime, date
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AmazonCsvImportReplacementLine(models.TransientModel):
    _name = 'amazon.csv.import.replacement.line'
    _description = 'Amazon CSV Import Replacement Line'

    wizard_id = fields.Many2one('amazon.csv.import.wizard', string="Wizard", required=True, ondelete='cascade')
    dashboard_record_id = fields.Many2one('amazon.dashboard.record', string="Dashboard Record", required=True, ondelete='cascade')
    order_id = fields.Char(string="Order ID", readonly=True)
    sku = fields.Char(string="SKU", readonly=True)
    item_description = fields.Text(string="Item Description", readonly=True)
    amount = fields.Float(string="Amount (Required)", required=True)
    reference_number = fields.Char(string="Reference Number")


class AmazonCsvImportWizard(models.TransientModel):
    _name = 'amazon.csv.import.wizard'
    _description = 'Import Amazon CSV/Excel File'

    state = fields.Selection([
        ('upload', 'Upload File'),
        ('result', 'Import Results & Log')
    ], default='upload', string="State")

    file_data = fields.Binary(string="CSV / Excel File")
    filename = fields.Char(string="File Name")

    # Import Result Metrics
    import_batch_id = fields.Char(string="Batch Number", readonly=True)
    total_rows = fields.Integer(string="Total Rows Processed", readonly=True)
    imported_count = fields.Integer(string="Successfully Imported", readonly=True)
    duplicate_count = fields.Integer(string="Duplicates Skipped", readonly=True)
    ignored_count = fields.Integer(string="Ignored (Cancel/Other)", readonly=True)
    log_details = fields.Text(string="Import Summary & Duplicate Log", readonly=True)

    replacement_line_ids = fields.One2many('amazon.csv.import.replacement.line', 'wizard_id', string="Replacement Orders")
    has_replacement_lines = fields.Boolean(string="Has Replacement Lines", compute='_compute_has_replacement_lines')

    @api.depends('replacement_line_ids')
    def _compute_has_replacement_lines(self):
        for wiz in self:
            wiz.has_replacement_lines = bool(wiz.replacement_line_ids)

    def _parse_datetime(self, val_str):
        if not val_str or not val_str.strip():
            return False
        val_str = val_str.strip()
        formats = [
            '%d-%m-%Y %H:%M',
            '%d-%m-%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
            '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%d-%m-%Y',
            '%d/%m/%Y',
            '%Y-%m-%d'
        ]
        for fmt in formats:
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                continue
        _logger.warning(f"Could not parse datetime: {val_str}")
        return False

    def _parse_float(self, val_str):
        if not val_str or not str(val_str).strip():
            return 0.0
        try:
            return float(str(val_str).strip().replace(',', ''))
        except ValueError:
            return 0.0

    def _clean_str_id(self, val_str):
        """ Clean scientific notation strings like '5.65083E+11' into integer strings '565083000000' """
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
                    # Avoid decoding zip headers via latin1
                    if encoding in ('latin1', 'cp1252') and file_bytes.startswith(b'PK\x03\x04'):
                        continue
                    text_content = file_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

            if not text_content:
                raise UserError(_("Could not decode file encoding. Please ensure it is a valid CSV or Excel file."))

            lines = [l for l in text_content.splitlines() if l.strip()]
            if not lines:
                raise UserError(_("Uploaded file is empty."))

            # Auto-detect delimiter (tab, comma, semicolon)
            first_line = lines[0]
            delimiter = '\t' if '\t' in first_line else (',' if ',' in first_line else ';')

            try:
                reader = csv.reader(lines, delimiter=delimiter)
                for row in reader:
                    if any(row):
                        rows.append([str(c).strip() for c in row])
            except Exception as ce:
                raise UserError(_("Could not parse file as CSV/TSV: %s") % ce)

        return rows

    def action_import(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("Please select a CSV or Excel file to upload."))

        try:
            file_bytes = base64.b64decode(self.file_data)
        except Exception as e:
            raise UserError(_("Error decoding uploaded file: %s") % e)

        rows = self._read_file_rows(file_bytes, self.filename)

        if not rows or len(rows) < 2:
            raise UserError(_("Uploaded file does not contain valid data rows."))

        header = rows[0]
        data_rows = rows[1:]

        # Standardize header names
        header_map = {}
        for idx, col in enumerate(header):
            clean_col = str(col).strip().lower().replace(' ', '_').replace('/', '_').replace('-', '_').replace('.', '')
            header_map[clean_col] = idx

        # Column Aliases
        if 'order_id' not in header_map and 'amazon_order_id' in header_map:
            header_map['order_id'] = header_map['amazon_order_id']
        if 'transaction_type' not in header_map and 'type' in header_map:
            header_map['transaction_type'] = header_map['type']

        # Header Validation: Ensure this is a valid Amazon report file
        required_headers = ['transaction_type', 'order_id']
        missing_headers = [h for h in required_headers if h not in header_map]
        if missing_headers:
            raise UserError(_("Invalid Amazon File Header: Missing essential column(s) '%s'. Please upload a valid Amazon Sales/Refund CSV/Excel report file.") % ", ".join(missing_headers))

        _logger.info(f"Importing Amazon report with headers: {list(header_map.keys())}")

        batch_id = fields.Datetime.now().strftime('BATCH-%Y%m%d-%H%M%S')
        created_records = self.env['amazon.dashboard.record']
        DashboardRecord = self.env['amazon.dashboard.record']

        total_rows = 0
        imported_count = 0
        duplicate_count = 0
        ignored_count = 0
        log_lines = []

        for row in data_rows:
            if not row or not any(str(c).strip() for c in row if c is not None):
                continue

            total_rows += 1

            def get_val(key, is_id=False):
                idx = header_map.get(key)
                if idx is not None and idx < len(row):
                    val = str(row[idx]).strip() if row[idx] is not None else ''
                    if is_id and val:
                        return self._clean_str_id(val)
                    return val
                return ''

            tx_type = get_val('transaction_type')
            order_id = get_val('order_id', is_id=True)
            inv_num = get_val('invoice_number', is_id=True)
            sku = get_val('sku', is_id=True)
            cn_no = get_val('credit_note_no', is_id=True)

            # Allow Shipment, Refund, Cancel, and FreeReplacement transaction types
            if tx_type not in ('Shipment', 'Refund', 'Cancel', 'FreeReplacement'):
                ignored_count += 1
                continue

            # Duplicate Check across existing database records
            dup_domain = [
                ('transaction_type', '=', tx_type),
                ('order_id', '=', order_id),
            ]
            if inv_num:
                dup_domain.append(('invoice_number', '=', inv_num))
            if sku:
                dup_domain.append(('sku', '=', sku))
            if tx_type == 'Refund' and cn_no:
                dup_domain.append(('credit_note_no', '=', cn_no))

            existing = DashboardRecord.search(dup_domain, limit=1)
            if existing:
                duplicate_count += 1
                log_lines.append(f"• [Dup Skipped] Order ID: {order_id} | Invoice: {inv_num or 'N/A'} | SKU: {sku} | Type: {tx_type}")
                continue

            try:
                vals = {
                    'import_batch_id': batch_id,
                    'seller_gstin': get_val('seller_gstin'),
                    'invoice_number': inv_num,
                    'invoice_date': self._parse_datetime(get_val('invoice_date')),
                    'transaction_type': tx_type,
                    'order_id': order_id,
                    'shipment_id': get_val('shipment_id', is_id=True),
                    'shipment_date': self._parse_datetime(get_val('shipment_date')),
                    'order_date': self._parse_datetime(get_val('order_date')),
                    'shipment_item_id': get_val('shipment_item_id', is_id=True),
                    'quantity': self._parse_float(get_val('quantity')) or 1.0,
                    'item_description': get_val('item_description'),
                    'asin': get_val('asin', is_id=True),
                    'hsn_sac': get_val('hsn_sac', is_id=True) or get_val('hsn', is_id=True),
                    'sku': sku,
                    'product_tax_code': get_val('product_tax_code'),
                    
                    'bill_from_city': get_val('bill_from_city'),
                    'bill_from_state': get_val('bill_from_state'),
                    'ship_from_city': get_val('ship_from_city'),
                    'ship_from_state': get_val('ship_from_state'),
                    'ship_to_city': get_val('ship_to_city'),
                    'ship_to_state': get_val('ship_to_state'),

                    'invoice_amount': self._parse_float(get_val('invoice_amount')),
                    'tax_exclusive_gross': self._parse_float(get_val('tax_exclusive_gross')),
                    'total_tax_amount': self._parse_float(get_val('total_tax_amount')),
                    'cgst_rate': self._parse_float(get_val('cgst_rate')),
                    'sgst_rate': self._parse_float(get_val('sgst_rate')),
                    'utgst_rate': self._parse_float(get_val('utgst_rate')),
                    'igst_rate': self._parse_float(get_val('igst_rate')),
                    'principal_amount': self._parse_float(get_val('principal_amount')),
                    'principal_amount_basis': self._parse_float(get_val('principal_amount_basis')),
                    'cgst_tax': self._parse_float(get_val('cgst_tax')),
                    'sgst_tax': self._parse_float(get_val('sgst_tax')),
                    'igst_tax': self._parse_float(get_val('igst_tax')),
                    'utgst_tax': self._parse_float(get_val('utgst_tax')),

                    'tcs_cgst_rate': self._parse_float(get_val('tcs_cgst_rate')),
                    'tcs_cgst_amount': self._parse_float(get_val('tcs_cgst_amount')),
                    'tcs_sgst_rate': self._parse_float(get_val('tcs_sgst_rate')),
                    'tcs_sgst_amount': self._parse_float(get_val('tcs_sgst_amount')),
                    'tcs_utgst_rate': self._parse_float(get_val('tcs_utgst_rate')),
                    'tcs_utgst_amount': self._parse_float(get_val('tcs_utgst_amount')),
                    'tcs_igst_rate': self._parse_float(get_val('tcs_igst_rate')),
                    'tcs_igst_amount': self._parse_float(get_val('tcs_igst_amount')),

                    'credit_note_no': cn_no,
                    'credit_note_date': self._parse_datetime(get_val('credit_note_date')),
                    'state': 'draft',
                }

                record = DashboardRecord.create(vals)
                created_records |= record
                imported_count += 1

                if tx_type == 'FreeReplacement':
                    parsed_amt = self._parse_float(get_val('tax_exclusive_gross')) or self._parse_float(get_val('invoice_amount'))
                    self.env['amazon.csv.import.replacement.line'].create({
                        'wizard_id': self.id,
                        'dashboard_record_id': record.id,
                        'order_id': order_id,
                        'sku': sku,
                        'item_description': get_val('item_description'),
                        'amount': parsed_amt,
                        'reference_number': cn_no,
                    })
            except Exception as pe:
                log_lines.append(f"• [PARSE ERROR] Order ID: {order_id} | Error: {pe}")

        log_content = "\n".join(log_lines) if log_lines else "No duplicate records or errors encountered."

        self.write({
            'state': 'result',
            'import_batch_id': batch_id,
            'total_rows': total_rows,
            'imported_count': imported_count,
            'duplicate_count': duplicate_count,
            'ignored_count': ignored_count,
            'log_details': log_content,
        })

        return {
            'name': _('Upload Summary & Duplicate Log'),
            'type': 'ir.actions.act_window',
            'res_model': 'amazon.csv.import.wizard',
            'res_id': self.id,
            'views': [(False, 'form')],
            'view_mode': 'form',
            'target': 'new',
        }

    def action_save_replacement_details(self):
        self.ensure_one()
        for line in self.replacement_line_ids:
            if not line.amount or line.amount <= 0:
                raise UserError(_("Amount is required for replacement record Order ID '%s' (SKU: %s). Please enter a valid amount before completing import.") % (line.order_id, line.sku or 'N/A'))
            
            if line.dashboard_record_id:
                line.dashboard_record_id.write({
                    'tax_exclusive_gross': line.amount,
                    'invoice_amount': line.amount,
                    'principal_amount': line.amount,
                    'credit_note_no': line.reference_number or '',
                })
        return {'type': 'ir.actions.act_window_close'}
