# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AmazonDashboardRecord(models.Model):
    _name = 'amazon.dashboard.record'
    _description = 'Amazon Dashboard Transaction Record'
    _order = 'order_date desc, id desc'

    name = fields.Char(string="Record Title", compute='_compute_name', store=True)
    import_batch_id = fields.Char(string="Import Batch ID", index=True)
    seller_gstin = fields.Char(string="Seller GSTIN")
    invoice_number = fields.Char(string="Invoice Number", index=True)
    invoice_date = fields.Datetime(string="Invoice Date")
    transaction_type = fields.Selection([
        ('Shipment', 'Shipment'),
        ('Refund', 'Refund')
    ], string="Transaction Type", required=True, index=True)
    order_id = fields.Char(string="Order ID", index=True)
    shipment_id = fields.Char(string="Shipment ID", index=True)
    shipment_date = fields.Datetime(string="Shipment Date")
    order_date = fields.Datetime(string="Order Date")
    shipment_item_id = fields.Char(string="Shipment Item ID")
    quantity = fields.Float(string="Quantity", default=1.0)
    item_description = fields.Text(string="Item Description")
    asin = fields.Char(string="ASIN")
    hsn_sac = fields.Char(string="HSN/SAC")
    sku = fields.Char(string="SKU", index=True)
    product_tax_code = fields.Char(string="Product Tax Code")

    # Address fields
    bill_from_city = fields.Char(string="Bill From City")
    bill_from_state = fields.Char(string="Bill From State")
    ship_from_city = fields.Char(string="Ship From City")
    ship_from_state = fields.Char(string="Ship From State")
    ship_to_city = fields.Char(string="Ship To City")
    ship_to_state = fields.Char(string="Ship To State")

    # 3 Summary Address fields (City, State)
    bill_from = fields.Char(string="Bill From", compute='_compute_address_summaries', store=True)
    ship_from = fields.Char(string="Ship From", compute='_compute_address_summaries', store=True)
    ship_to = fields.Char(string="Ship To", compute='_compute_address_summaries', store=True)

    # Monetary and Tax Breakdown
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)
    invoice_amount = fields.Monetary(string="Invoice Amount")
    tax_exclusive_gross = fields.Monetary(string="Tax Exclusive Gross (Price Base)")
    total_tax_amount = fields.Monetary(string="Total Tax Amount")
    cgst_rate = fields.Float(string="CGST Rate (%)")
    sgst_rate = fields.Float(string="SGST Rate (%)")
    utgst_rate = fields.Float(string="UTGST Rate (%)")
    igst_rate = fields.Float(string="IGST Rate (%)")
    principal_amount = fields.Monetary(string="Principal Amount")
    principal_amount_basis = fields.Monetary(string="Principal Amount Basis")
    cgst_tax = fields.Monetary(string="CGST Tax")
    sgst_tax = fields.Monetary(string="SGST Tax")
    igst_tax = fields.Monetary(string="IGST Tax")
    utgst_tax = fields.Monetary(string="UTGST Tax")

    # TCS Tax fields
    tcs_cgst_rate = fields.Float(string="TCS CGST Rate")
    tcs_cgst_amount = fields.Monetary(string="TCS CGST Amount")
    tcs_sgst_rate = fields.Float(string="TCS SGST Rate")
    tcs_sgst_amount = fields.Monetary(string="TCS SGST Amount")
    tcs_utgst_rate = fields.Float(string="TCS UTGST Rate")
    tcs_utgst_amount = fields.Monetary(string="TCS UTGST Amount")
    tcs_igst_rate = fields.Float(string="TCS IGST Rate")
    tcs_igst_amount = fields.Monetary(string="TCS IGST Amount")

    # Credit Note fields for Refund
    credit_note_no = fields.Char(string="Credit Note No")
    credit_note_date = fields.Datetime(string="Credit Note Date")

    # Relational Links
    product_id = fields.Many2one('product.product', string="Mapped Product")
    sale_order_id = fields.Many2one('sale.order', string="Created Sale Order")
    picking_id = fields.Many2one('stock.picking', string="Created Delivery Picking")
    invoice_id = fields.Many2one('account.move', string="Created Invoice")
    refund_move_id = fields.Many2one('account.move', string="Created Refund (Credit Note)")

    # Status
    state = fields.Selection([
        ('draft', 'Pending'),
        ('so_created', 'SO Created'),
        ('refund_created', 'Refund Created'),
        ('error', 'Error')
    ], string="Status", default='draft', required=True, index=True)
    error_message = fields.Text(string="Error Log")

    @api.depends('order_id', 'sku', 'transaction_type')
    def _compute_name(self):
        for rec in self:
            rec.name = f"[{rec.transaction_type or 'Record'}] Order #{rec.order_id or 'N/A'} - SKU: {rec.sku or 'N/A'}"

    @api.depends('bill_from_city', 'bill_from_state', 'ship_from_city', 'ship_from_state', 'ship_to_city', 'ship_to_state')
    def _compute_address_summaries(self):
        for rec in self:
            rec.bill_from = f"{rec.bill_from_city or ''}, {rec.bill_from_state or ''}".strip(', ')
            rec.ship_from = f"{rec.ship_from_city or ''}, {rec.ship_from_state or ''}".strip(', ')
            rec.ship_to = f"{rec.ship_to_city or ''}, {rec.ship_to_state or ''}".strip(', ')

    def action_open_record_wizard(self):
        """ Opens a form view window displaying full granular record fields """
        self.ensure_one()
        return {
            'name': _('Amazon Transaction Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'amazon.dashboard.record',
            'res_id': self.id,
            'views': [(False, 'form')],
            'view_mode': 'form',
            'target': 'new',
        }

    def _find_product_by_sku(self, sku, item_description, hsn_sac, asin, product_tax_code):
        """ Searches product strictly by SKU (default_code). Raises UserError if not found (does NOT create product). """
        Product = self.env['product.product']
        if not sku or not sku.strip():
            raise UserError(_("SKU is missing for Order ID %s.") % (self.order_id or 'N/A'))

        clean_sku = sku.strip()
        product = Product.search([('default_code', '=', clean_sku)], limit=1)
        if not product:
            raise UserError(_("Product not found in Odoo for SKU '%s'. Please create or configure a product with Internal Reference '%s' in Odoo.") % (clean_sku, clean_sku))

        # Update ASIN & Product Tax Code on found product if missing
        vals = {}
        if asin and not product.asin:
            vals['asin'] = asin
        if product_tax_code and not product.product_tax_code:
            vals['product_tax_code'] = product_tax_code
        if vals:
            product.write(vals)

        return product

    def _find_matching_taxes(self, company_id, cgst_rate, sgst_rate, igst_rate, utgst_rate):
        """ Searches for sales tax in account.tax based on rates in decimal (e.g. 0.18 = 18%) """
        Tax = self.env['account.tax']
        domain = [
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', company_id.id),
        ]
        
        matched_taxes = self.env['account.tax']

        # Convert rates to percentage integer/float
        igst_pct = round(igst_rate * 100, 2) if igst_rate else 0.0
        cgst_pct = round(cgst_rate * 100, 2) if cgst_rate else 0.0
        sgst_pct = round(sgst_rate * 100, 2) if sgst_rate else 0.0
        utgst_pct = round(utgst_rate * 100, 2) if utgst_rate else 0.0

        if igst_pct > 0:
            taxes = Tax.search(domain + [('amount', '=', igst_pct)])
            # Prefer IGST in name if available
            igst_tax = taxes.filtered(lambda t: 'IGST' in t.name.upper() or 'GST' in t.name.upper())
            if igst_tax:
                matched_taxes |= igst_tax[:1]
            elif taxes:
                matched_taxes |= taxes[:1]
        
        if cgst_pct > 0:
            cgst_tax = Tax.search(domain + [('amount', '=', cgst_pct)]).filtered(lambda t: 'CGST' in t.name.upper())
            if cgst_tax:
                matched_taxes |= cgst_tax[:1]

        if sgst_pct > 0 or utgst_pct > 0:
            sg_rate = sgst_pct or utgst_pct
            sgst_tax = Tax.search(domain + [('amount', '=', sg_rate)]).filtered(lambda t: ('SGST' in t.name.upper() or 'UTGST' in t.name.upper()))
            if sgst_tax:
                matched_taxes |= sgst_tax[:1]

        # Fallback: Total percentage match if specific components not found
        if not matched_taxes:
            tot_pct = round((igst_pct or (cgst_pct + sgst_pct + utgst_pct)), 2)
            if tot_pct > 0:
                tot_taxes = Tax.search(domain + [('amount', '=', tot_pct)], limit=1)
                if tot_taxes:
                    matched_taxes |= tot_taxes

        return matched_taxes

    def _get_or_create_partner(self, state_name):
        """ Find or create Amazon customer partner: 'Amazon intra' for Kerala, 'Amazon inter' for Non-Kerala """
        Partner = self.env['res.partner']
        State = self.env['res.country.state']

        st_clean = (state_name or '').strip().lower()
        is_kerala = 'kerala' in st_clean or st_clean in ('kl', 'kerala')

        partner_name = "Amazon intra" if is_kerala else "Amazon inter"
        partner = Partner.search([('name', '=', partner_name)], limit=1)

        if not partner:
            state_rec = False
            if is_kerala:
                state_rec = State.search([('name', 'ilike', 'Kerala'), ('country_id.code', '=', 'IN')], limit=1)
            elif state_name and state_name.strip():
                state_rec = State.search([('name', 'ilike', state_name.strip()), ('country_id.code', '=', 'IN')], limit=1)

            india = self.env['res.country'].search([('code', '=', 'IN')], limit=1)
            partner = Partner.create({
                'name': partner_name,
                'customer_rank': 1,
                'is_company': True,
                'state_id': state_rec.id if state_rec else False,
                'country_id': india.id if india else False,
            })

        return partner

    def action_create_sale_order(self):
        """ Create Sale Order + Delivery Picking + Invoice for Shipment transaction """
        for rec in self:
            if rec.transaction_type != 'Shipment':
                raise UserError(_("Record %s is not a Shipment transaction.") % rec.name)
            if rec.sale_order_id:
                raise UserError(_("Sale Order already exists for %s: %s") % (rec.name, rec.sale_order_id.name))

            try:
                company = self.env.company
                product = rec._find_product_by_sku(rec.sku, rec.item_description, rec.hsn_sac, rec.asin, rec.product_tax_code)
                rec.product_id = product.id

                partner = rec._get_or_create_partner(rec.ship_to_state)
                taxes = rec._find_matching_taxes(company, rec.cgst_rate, rec.sgst_rate, rec.igst_rate, rec.utgst_rate)

                qty = rec.quantity if rec.quantity > 0 else 1.0
                unit_price = abs(rec.tax_exclusive_gross / qty) if rec.tax_exclusive_gross else 0.0

                so_vals = {
                    'partner_id': partner.id,
                    'date_order': rec.order_date or fields.Datetime.now(),
                    'amazon_order_id': rec.order_id,
                    'amazon_shipment_id': rec.shipment_id,
                    'client_order_ref': rec.shipment_id or rec.order_id,
                    'origin': rec.shipment_id or f"Amazon Order {rec.order_id}",
                    'order_line': [(0, 0, {
                        'product_id': product.id,
                        'name': rec.item_description or product.name,
                        'product_uom_qty': qty,
                        'product_uom_id': product.uom_id.id if product.uom_id else False,
                        'price_unit': unit_price,
                        'tax_ids': [(6, 0, taxes.ids)],
                    })],
                }

                so = self.env['sale.order'].create(so_vals)
                so.action_confirm()

                # Update Picking
                picking = so.picking_ids[:1]
                if picking:
                    if rec.shipment_date:
                        picking.scheduled_date = rec.shipment_date
                    picking.amazon_shipment_id = rec.shipment_id
                    
                    # Update stock moves
                    for move in picking.move_ids:
                        move.amazon_shipment_item_id = rec.shipment_item_id
                        move.quantity = qty

                    # Attempt picking validation
                    try:
                        picking.button_validate()
                    except Exception as pe:
                        _logger.warning(f"Could not auto-validate picking {picking.name}: {pe}")

                # Create & Post Invoice
                invoice = so._create_invoices()
                if invoice:
                    invoice.write({
                        'amazon_invoice_number': rec.invoice_number,
                        'amazon_order_id': rec.order_id,
                        'ref': rec.invoice_number or rec.order_id,
                    })
                    if rec.invoice_date:
                        invoice.invoice_date = rec.invoice_date.date()
                    try:
                        invoice.action_post()
                    except Exception as ie:
                        _logger.warning(f"Could not auto-post invoice {invoice.name}: {ie}")

                rec.write({
                    'sale_order_id': so.id,
                    'picking_id': picking.id if picking else False,
                    'invoice_id': invoice.id if invoice else False,
                    'state': 'so_created',
                    'error_message': False,
                })

            except Exception as e:
                _logger.exception(f"Error creating Sale Order for record {rec.id}: {e}")
                rec.write({
                    'state': 'error',
                    'error_message': str(e)
                })

    def action_create_refund(self):
        """ Create & Link Refund (Credit Note) for Refund transaction """
        for rec in self:
            if rec.transaction_type != 'Refund':
                raise UserError(_("Record %s is not a Refund transaction.") % rec.name)
            if rec.refund_move_id:
                raise UserError(_("Refund already exists for %s: %s") % (rec.name, rec.refund_move_id.name))

            try:
                company = self.env.company
                # Step 1: Check if there is an existing Sale Order or Invoice matching Order ID or Invoice Number across all historical records
                origin_so = self.env['sale.order'].search([('amazon_order_id', '=', rec.order_id)], limit=1)
                origin_inv = self.env['account.move'].search([
                    ('move_type', '=', 'out_invoice'),
                    '|',
                    ('amazon_invoice_number', '=', rec.invoice_number),
                    ('amazon_order_id', '=', rec.order_id)
                ], limit=1)

                partner = origin_inv.partner_id or origin_so.partner_id or rec._get_or_create_partner(rec.ship_to_state)
                product = rec._find_product_by_sku(rec.sku, rec.item_description, rec.hsn_sac, rec.asin, rec.product_tax_code)
                rec.product_id = product.id

                taxes = rec._find_matching_taxes(company, rec.cgst_rate, rec.sgst_rate, rec.igst_rate, rec.utgst_rate)
                qty = abs(rec.quantity) if rec.quantity else 1.0
                unit_price = abs(rec.tax_exclusive_gross / qty) if rec.tax_exclusive_gross else 0.0

                refund_vals = {
                    'move_type': 'out_refund',
                    'partner_id': partner.id,
                    'amazon_order_id': rec.order_id,
                    'amazon_invoice_number': rec.invoice_number,
                    'credit_note_no': rec.credit_note_no,
                    'credit_note_date': rec.credit_note_date,
                    'ref': rec.credit_note_no or rec.invoice_number or rec.order_id,
                    'invoice_date': rec.credit_note_date.date() if rec.credit_note_date else (rec.invoice_date.date() if rec.invoice_date else fields.Date.today()),
                    'invoice_line_ids': [(0, 0, {
                        'product_id': product.id,
                        'name': rec.item_description or f"Refund for Order {rec.order_id}",
                        'quantity': qty,
                        'price_unit': unit_price,
                        'tax_ids': [(6, 0, taxes.ids)],
                    })],
                }

                if origin_inv:
                    refund_vals['reversed_entry_id'] = origin_inv.id

                refund_move = self.env['account.move'].create(refund_vals)
                try:
                    refund_move.action_post()
                except Exception as re:
                    _logger.warning(f"Could not auto-post credit note {refund_move.name}: {re}")

                rec.write({
                    'refund_move_id': refund_move.id,
                    'state': 'refund_created',
                    'error_message': False,
                })

            except Exception as e:
                _logger.exception(f"Error creating Refund for record {rec.id}: {e}")
                rec.write({
                    'state': 'error',
                    'error_message': str(e)
                })

    def action_bulk_create_sale_orders(self):
        """ Bulk action to create sale orders for all selected shipment records """
        shipment_recs = self.filtered(lambda r: r.transaction_type == 'Shipment' and r.state in ('draft', 'error'))
        for r in shipment_recs:
            r.action_create_sale_order()

    def action_bulk_create_refunds(self):
        """ Bulk action to create refunds for all selected refund records """
        refund_recs = self.filtered(lambda r: r.transaction_type == 'Refund' and r.state in ('draft', 'error'))
        for r in refund_recs:
            r.action_create_refund()

    @api.model
    def action_process_selected(self, record_ids):
        """ Process multi-selected records based on transaction_type """
        if not record_ids:
            return False
        records = self.browse(record_ids)
        shipments = records.filtered(lambda r: r.transaction_type == 'Shipment' and r.state in ('draft', 'error'))
        refunds = records.filtered(lambda r: r.transaction_type == 'Refund' and r.state in ('draft', 'error'))
        
        for s in shipments:
            s.action_create_sale_order()
            
        for r in refunds:
            r.action_create_refund()

        return True

    @api.model
    def get_dashboard_data(self):
        """ API method for dynamic JS/OWL dashboard - displays only latest uploaded batch """
        latest_rec = self.search([('import_batch_id', '!=', False)], order='id desc', limit=1)
        if latest_rec and latest_rec.import_batch_id:
            records = self.search([('import_batch_id', '=', latest_rec.import_batch_id)], order='order_date desc, id desc')
        else:
            records = self.search([], order='order_date desc, id desc')

        shipments = records.filtered(lambda r: r.transaction_type == 'Shipment')
        refunds = records.filtered(lambda r: r.transaction_type == 'Refund')

        all_records_data = []
        for rec in records:
            dt_str = ''
            if rec.transaction_type == 'Refund' and rec.credit_note_date:
                dt_str = rec.credit_note_date.strftime('%d-%m-%Y %H:%M')
            elif rec.order_date:
                dt_str = rec.order_date.strftime('%d-%m-%Y %H:%M')

            doc_name = ''
            if rec.sale_order_id:
                doc_name = rec.sale_order_id.name
            elif rec.refund_move_id:
                doc_name = rec.refund_move_id.name

            all_records_data.append({
                'id': rec.id,
                'transaction_type': rec.transaction_type,
                'order_id': rec.order_id or '',
                'invoice_number': rec.invoice_number or '',
                'credit_note_no': rec.credit_note_no or '',
                'order_date': dt_str,
                'sku': rec.sku or '',
                'quantity': rec.quantity,
                'tax_exclusive_gross': round(rec.tax_exclusive_gross, 2),
                'total_tax_amount': round(rec.total_tax_amount, 2),
                'invoice_amount': round(rec.invoice_amount, 2),
                'ship_to': rec.ship_to or '',
                'state': rec.state,
                'error_message': rec.error_message or '',
                'odoo_document_name': doc_name,
                'import_batch_id': rec.import_batch_id or '',
            })

        kpis = {
            'total_shipments_count': len(shipments),
            'total_shipment_amount': round(sum(shipments.mapped('invoice_amount')), 2),
            'pending_shipments_count': len(shipments.filtered(lambda s: s.state in ('draft', 'error'))),
            'total_refunds_count': len(refunds),
            'total_refund_amount': round(sum(refunds.mapped('invoice_amount')), 2),
            'pending_refunds_count': len(refunds.filtered(lambda r: r.state in ('draft', 'error'))),
            'currency_symbol': self.env.company.currency_id.symbol or '₹',
            'latest_batch_id': latest_rec.import_batch_id if (latest_rec and latest_rec.import_batch_id) else 'Latest Upload',
        }

        return {
            'kpis': kpis,
            'all_records': all_records_data,
        }
