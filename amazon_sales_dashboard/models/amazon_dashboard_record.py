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

    def _find_matching_taxes(self, company_id, cgst_rate, sgst_rate, igst_rate, utgst_rate, is_intra=False):
        """
        Finds appropriate GST sales taxes in Odoo account.tax:
        - If is_intra (Intra-state: Kerala to Kerala / 'Amazon intra'):
          Applies CGST + SGST (e.g. 9% CGST + 9% SGST for 18% item). NEVER applies IGST!
        - If not is_intra (Inter-state: Kerala to Outside / 'Amazon inter'):
          Applies IGST (e.g. 18% IGST for 18% item). NEVER applies CGST/SGST!
        """
        Tax = self.env['account.tax']
        domain = [
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', company_id.id),
        ]
        
        matched_taxes = self.env['account.tax']

        # Fallback auto-calc tax rate from tax amount / price gross if rate is 0
        gross = self.tax_exclusive_gross or (self.invoice_amount - self.total_tax_amount if self.invoice_amount > self.total_tax_amount else 0.0)
        if gross > 0:
            if not igst_rate and self.igst_tax > 0:
                igst_rate = self.igst_tax / gross
            if not cgst_rate and self.cgst_tax > 0:
                cgst_rate = self.cgst_tax / gross
            if not sgst_rate and self.sgst_tax > 0:
                sgst_rate = self.sgst_tax / gross
            if not utgst_rate and self.utgst_tax > 0:
                utgst_rate = self.utgst_tax / gross
            if not igst_rate and not cgst_rate and not sgst_rate and self.total_tax_amount > 0:
                tot_r = self.total_tax_amount / gross
                if is_intra:
                    cgst_rate = tot_r / 2.0
                    sgst_rate = tot_r / 2.0
                else:
                    igst_rate = tot_r

        # Determine total tax percentage (e.g. 18%, 5%, 12%, 28%)
        igst_pct = round(igst_rate * 100, 2) if (0 < igst_rate <= 1.0) else round(igst_rate, 2)
        cgst_pct = round(cgst_rate * 100, 2) if (0 < cgst_rate <= 1.0) else round(cgst_rate, 2)
        sgst_pct = round(sgst_rate * 100, 2) if (0 < sgst_rate <= 1.0) else round(sgst_rate, 2)
        utgst_pct = round(utgst_rate * 100, 2) if (0 < utgst_rate <= 1.0) else round(utgst_rate, 2)

        tot_tax_pct = igst_pct or (cgst_pct + sgst_pct + utgst_pct)

        if is_intra:
            # --- INTRA-STATE (Amazon intra: Kerala -> Kerala) ---
            # MUST apply CGST + SGST (or Group Tax). CANNOT apply IGST!
            half_pct = round(tot_tax_pct / 2.0, 2) if tot_tax_pct else (cgst_pct or sgst_pct)

            if half_pct > 0:
                # 1. Look for CGST tax (e.g. amount == 9.0%, name contains 'CGST')
                cgst_taxes = Tax.search(domain + [('amount', '=', half_pct)]).filtered(lambda t: 'CGST' in t.name.upper())
                if cgst_taxes:
                    matched_taxes |= cgst_taxes[:1]

                # 2. Look for SGST / UTGST tax (e.g. amount == 9.0%, name contains 'SGST' or 'UTGST')
                sgst_taxes = Tax.search(domain + [('amount', '=', half_pct)]).filtered(lambda t: ('SGST' in t.name.upper() or 'UTGST' in t.name.upper()))
                if sgst_taxes:
                    matched_taxes |= sgst_taxes[:1]

            # 3. Fallback: Look for Intra Group Tax
            if not matched_taxes and tot_tax_pct > 0:
                group_taxes = Tax.search(domain + [('amount_type', '=', 'group')]).filtered(lambda t: 'IGST' not in t.name.upper() and ('CGST' in t.name.upper() or 'SGST' in t.name.upper() or 'GST' in t.name.upper()))
                if group_taxes:
                    matched_taxes |= group_taxes[:1]

        else:
            # --- INTER-STATE (Amazon inter: Kerala -> Outside Kerala) ---
            # MUST apply IGST. CANNOT apply CGST/SGST split!
            if tot_tax_pct > 0:
                igst_taxes = Tax.search(domain + [('amount', '=', tot_tax_pct)]).filtered(lambda t: 'IGST' in t.name.upper())
                if not igst_taxes:
                    igst_taxes = Tax.search(domain + [('amount', '=', tot_tax_pct)]).filtered(lambda t: 'INTER' in t.name.upper() or 'OUTSIDE' in t.name.upper())
                if not igst_taxes:
                    igst_taxes = Tax.search(domain + [('amount', '=', tot_tax_pct)])
                if igst_taxes:
                    matched_taxes |= igst_taxes[:1]

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

                st_clean = (rec.ship_to_state or '').strip().lower()
                is_intra = 'kerala' in st_clean or st_clean in ('kl', 'kerala')

                partner = rec._get_or_create_partner(rec.ship_to_state)
                taxes = rec._find_matching_taxes(company, rec.cgst_rate, rec.sgst_rate, rec.igst_rate, rec.utgst_rate, is_intra=is_intra)

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
                        'name': rec.item_description or f"Amazon Item {rec.sku}",
                        'product_uom_qty': qty,
                        'price_unit': unit_price,
                        'tax_ids': [(6, 0, taxes.ids)] if taxes else False,
                    })],
                }

                so = self.env['sale.order'].create(so_vals)
                so.action_confirm()

                # Auto Process Delivery Picking
                for picking in so.picking_ids:
                    if picking.state not in ('done', 'cancel'):
                        for move in picking.move_ids:
                            move.quantity = move.product_uom_qty
                        try:
                            picking.button_validate()
                        except Exception as pe:
                            _logger.warning(f"Could not auto-validate picking {picking.name}: {pe}")

                # Auto Create & Post Invoice
                invoice = so._create_invoices()
                if invoice:
                    invoice.write({
                        'amazon_order_id': rec.order_id,
                        'amazon_invoice_number': rec.invoice_number,
                        'ref': rec.invoice_number or rec.shipment_id or rec.order_id,
                        'invoice_date': rec.invoice_date.date() if rec.invoice_date else fields.Date.today(),
                    })
                    try:
                        invoice.action_post()
                    except Exception as ie:
                        _logger.warning(f"Could not auto-post invoice {invoice.name}: {ie}")

                rec.write({
                    'sale_order_id': so.id,
                    'state': 'so_created',
                    'error_message': False,
                })

                return {
                    'res_id': so.id,
                    'name': so.name,
                }

            except Exception as e:
                _logger.exception(f"Error creating Sale Order for record {rec.id}: {e}")
                rec.write({
                    'state': 'error',
                    'error_message': str(e)
                })
                raise UserError(_("Could not create Sale Order for Order '%s': %s") % (rec.order_id, e))

    def action_create_refund(self, force_direct=False):
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

                # Step 2: Check Amazon transaction history for matching Shipment record
                shipment_history = self.search([
                    ('transaction_type', '=', 'Shipment'),
                    '|',
                    ('order_id', '=', rec.order_id),
                    ('invoice_number', '=', rec.invoice_number)
                ], limit=1)

                # Step 3: Interactive Confirmation Wizard if force_direct is False and Sale Order/Invoice is not created yet
                if not force_direct and not origin_so and not origin_inv:
                    if shipment_history and shipment_history.state != 'so_created':
                        wiz = self.env['amazon.refund.confirmation.wizard'].create({
                            'record_id': rec.id,
                            'shipment_record_id': shipment_history.id,
                            'wizard_type': 'so_pending',
                            'message': _("Sale Order for Order ID '%s' (Invoice: %s) has not been created yet.\n\nClick 'Create Sale Order First & Refund' to process the shipment first, or click 'Create Direct Credit Note'.") % (rec.order_id, rec.invoice_number or 'N/A'),
                        })
                        return {
                            'name': _('Refund Creation Confirmation'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'amazon.refund.confirmation.wizard',
                            'res_id': wiz.id,
                            'views': [(False, 'form')],
                            'view_mode': 'form',
                            'target': 'new',
                        }
                    elif not shipment_history:
                        wiz = self.env['amazon.refund.confirmation.wizard'].create({
                            'record_id': rec.id,
                            'wizard_type': 'no_so_found',
                            'message': _("No prior Sale Order or Shipment record found for Order ID '%s'.\n\nDo you want to create a direct standalone Credit Note?") % rec.order_id,
                        })
                        return {
                            'name': _('Refund Creation Confirmation'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'amazon.refund.confirmation.wizard',
                            'res_id': wiz.id,
                            'views': [(False, 'form')],
                            'view_mode': 'form',
                            'target': 'new',
                        }

                st_clean = (rec.ship_to_state or '').strip().lower()
                is_intra = 'kerala' in st_clean or st_clean in ('kl', 'kerala')

                partner = origin_inv.partner_id or origin_so.partner_id or rec._get_or_create_partner(rec.ship_to_state)
                product = rec._find_product_by_sku(rec.sku, rec.item_description, rec.hsn_sac, rec.asin, rec.product_tax_code)
                rec.product_id = product.id

                taxes = rec._find_matching_taxes(company, rec.cgst_rate, rec.sgst_rate, rec.igst_rate, rec.utgst_rate, is_intra=is_intra)
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
                        'tax_ids': [(6, 0, taxes.ids)] if taxes else False,
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

                return {
                    'res_id': refund_move.id,
                    'name': refund_move.name,
                }

            except Exception as e:
                _logger.exception(f"Error creating Refund for record {rec.id}: {e}")
                rec.write({
                    'state': 'error',
                    'error_message': str(e)
                })
                raise UserError(_("Could not create Refund for Order '%s': %s") % (rec.order_id, e))

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
    def get_dashboard_data(self, show_all=False):
        """ API method for dynamic JS/OWL dashboard - displays latest batch or all data """
        if show_all or self._context.get('show_all'):
            records = self.search([], order='order_date desc, id desc')
            batch_title = "All Historical Data"
        else:
            latest_rec = self.search([('import_batch_id', '!=', False)], order='id desc', limit=1)
            if latest_rec and latest_rec.import_batch_id:
                records = self.search([('import_batch_id', '=', latest_rec.import_batch_id)], order='order_date desc, id desc')
                batch_title = latest_rec.import_batch_id
            else:
                records = self.search([], order='order_date desc, id desc')
                batch_title = "Latest Upload"

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
            'latest_batch_id': batch_title,
        }

        return {
            'kpis': kpis,
            'all_records': all_records_data,
        }
