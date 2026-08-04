# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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

    def action_import(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("Please select a CSV or Excel file to upload."))

        try:
            file_bytes = base64.b64decode(self.file_data)
        except Exception as e:
            raise UserError(_("Error decoding uploaded file: %s") % e)

        # Decode content
        text_content = False
        for encoding in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
            try:
                text_content = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not text_content:
            raise UserError(_("Could not decode file encoding. Please ensure it is a valid CSV/Text file."))

        f = io.StringIO(text_content)
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise UserError(_("Uploaded file is empty."))

        # Standardize header names
        header_map = {}
        for idx, col in enumerate(header):
            clean_col = col.strip().lower().replace(' ', '_').replace('/', '_')
            header_map[clean_col] = idx

        _logger.info(f"Importing Amazon CSV with headers: {list(header_map.keys())}")

        batch_id = fields.Datetime.now().strftime('BATCH-%Y%m%d-%H%M%S')
        created_records = self.env['amazon.dashboard.record']
        DashboardRecord = self.env['amazon.dashboard.record']

        total_rows = 0
        imported_count = 0
        duplicate_count = 0
        ignored_count = 0
        log_lines = []

        for row in reader:
            if not row or not any(row):
                continue

            total_rows += 1

            def get_val(key):
                idx = header_map.get(key)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return ''

            tx_type = get_val('transaction_type')
            order_id = get_val('order_id')
            inv_num = get_val('invoice_number')
            sku = get_val('sku')
            cn_no = get_val('credit_note_no')

            # Filter ONLY Shipment and Refund transaction types (ignore Cancel and other types)
            if tx_type not in ('Shipment', 'Refund'):
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
                    'shipment_id': get_val('shipment_id'),
                    'shipment_date': self._parse_datetime(get_val('shipment_date')),
                    'order_date': self._parse_datetime(get_val('order_date')),
                    'shipment_item_id': get_val('shipment_item_id'),
                    'quantity': self._parse_float(get_val('quantity')) or 1.0,
                    'item_description': get_val('item_description'),
                    'asin': get_val('asin'),
                    'hsn_sac': get_val('hsn_sac') or get_val('hsn'),
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
