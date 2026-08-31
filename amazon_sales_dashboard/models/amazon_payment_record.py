# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AmazonPaymentRecord(models.Model):
    _name = 'amazon.payment.record'
    _description = 'Amazon Payment Settlement Record'
    _order = 'posted_date_time desc, id desc'

    name = fields.Char(string="Record Title", compute='_compute_name', store=True)
    import_batch_id = fields.Char(string="Import Batch ID", index=True)
    
    # Settlement Header Info
    settlement_id = fields.Char(string="Settlement ID", index=True)
    settlement_start_date = fields.Datetime(string="Settlement Start Date")
    settlement_end_date = fields.Datetime(string="Settlement End Date")
    deposit_date = fields.Datetime(string="Deposit Date")
    total_amount = fields.Monetary(string="Total Settlement Amount")
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)
    currency_code = fields.Char(string="Currency Code")
    
    # Transaction Info
    transaction_type = fields.Char(string="Transaction Type", index=True)
    order_id = fields.Char(string="Order ID", index=True)
    merchant_order_id = fields.Char(string="Merchant Order ID")
    adjustment_id = fields.Char(string="Adjustment ID")
    shipment_id = fields.Char(string="Shipment ID")
    marketplace_name = fields.Char(string="Marketplace Name")
    
    # Amount Details
    amount_type = fields.Char(string="Amount Type")
    amount_description = fields.Char(string="Amount Description", index=True)
    amount = fields.Monetary(string="Amount")
    
    # Item & Fulfillment Info
    fulfillment_id = fields.Char(string="Fulfillment ID")
    posted_date = fields.Date(string="Posted Date")
    posted_date_time = fields.Datetime(string="Posted Date Time")
    order_item_code = fields.Char(string="Order Item Code")
    merchant_order_item_id = fields.Char(string="Merchant Order Item ID")
    merchant_adjustment_item_id = fields.Char(string="Merchant Adjustment Item ID")
    sku = fields.Char(string="SKU", index=True)
    quantity_purchased = fields.Float(string="Quantity Purchased", default=0.0)
    promotion_id = fields.Char(string="Promotion ID")

    # Workflow & Linking Status
    state = fields.Selection([
        ('draft', 'Imported / Draft'),
        ('posted', 'Validated'),
        ('journal_created', 'Journal Entry Created'),
        ('payment_created', 'Payment Created'),
    ], string="Status", default='draft', required=True, index=True)
    
    move_id = fields.Many2one('account.move', string="Created Journal Entry", readonly=True)
    payment_id = fields.Many2one('account.payment', string="Created Payment", readonly=True)
    vendor_bill_id = fields.Many2one('account.move', string="Created Vendor Bill", readonly=True)

    @api.depends('order_id', 'settlement_id', 'amount_description', 'amount')
    def _compute_name(self):
        for rec in self:
            desc = rec.amount_description or rec.amount_type or 'Payment Line'
            order = rec.order_id or rec.settlement_id or 'N/A'
            rec.name = f"[{order}] {desc}: {rec.amount}"

    @api.model
    def get_payment_dashboard_data(self, is_all=False, selected_order_id=None):
        """ Fetch data for OWL Payment Dashboard """
        domain = []
        if not is_all:
            latest_rec = self.search([], order='id desc', limit=1)
            if latest_rec and latest_rec.import_batch_id:
                domain.append(('import_batch_id', '=', latest_rec.import_batch_id))

        records = self.search(domain)
        latest_batch = records[0].import_batch_id if records else "No Data"

        # Overall KPIs
        total_payout = 0.0
        total_principal = 0.0
        total_product_tax = 0.0
        total_amazon_fees = 0.0
        total_withheld_taxes = 0.0
        field_totals_dict = {}

        distinct_orders = set()
        order_dict = {}
        all_order_ids = set()

        for rec in records:
            amt = rec.amount or 0.0
            total_payout += amt
            desc = (rec.amount_description or rec.amount_type or 'Other').strip()
            if not desc:
                desc = 'Other'
            desc_lower = desc.lower()

            field_totals_dict[desc] = field_totals_dict.get(desc, 0.0) + amt

            if rec.order_id:
                distinct_orders.add(rec.order_id)
                all_order_ids.add(rec.order_id)
                if rec.order_id not in order_dict:
                    order_dict[rec.order_id] = {
                        'order_id': rec.order_id,
                        'posted_date': fields.Date.to_string(rec.posted_date) if rec.posted_date else '',
                        'posted_date_time': fields.Datetime.to_string(rec.posted_date_time) if rec.posted_date_time else '',
                        'total_amount': 0.0,
                        'principal': 0.0,
                        'fees': 0.0,
                        'tax': 0.0,
                        'records_count': 0,
                        'descriptions': {},
                        'payment_id': rec.payment_id.id if rec.payment_id else False,
                        'payment_name': rec.payment_id.name if rec.payment_id else '',
                        'move_id': rec.move_id.id if rec.move_id else False,
                        'move_name': rec.move_id.name if rec.move_id else '',
                        'vendor_bill_id': rec.vendor_bill_id.id if rec.vendor_bill_id else False,
                        'vendor_bill_name': rec.vendor_bill_id.name if rec.vendor_bill_id else '',
                        'is_processed': rec.state == 'posted',
                    }
                
                ord_info = order_dict[rec.order_id]
                ord_info['total_amount'] += amt
                ord_info['records_count'] += 1

                if rec.payment_id and not ord_info.get('payment_id'):
                    ord_info['payment_id'] = rec.payment_id.id
                    ord_info['payment_name'] = rec.payment_id.name or f"Payment #{rec.payment_id.id}"
                if rec.move_id and not ord_info.get('move_id'):
                    ord_info['move_id'] = rec.move_id.id
                    ord_info['move_name'] = rec.move_id.name or f"Entry #{rec.move_id.id}"
                if rec.vendor_bill_id and not ord_info.get('vendor_bill_id'):
                    ord_info['vendor_bill_id'] = rec.vendor_bill_id.id
                    ord_info['vendor_bill_name'] = rec.vendor_bill_id.name or f"Bill #{rec.vendor_bill_id.id}"
                
                # Breakdown by description
                if desc not in ord_info['descriptions']:
                    ord_info['descriptions'][desc] = 0.0
                ord_info['descriptions'][desc] += amt

            # Categorize KPI & order amounts (excluding TCS & TDS from Sales & Fees)
            if any(k in desc_lower for k in ['tcs', 'tds']):
                total_withheld_taxes += amt
            elif desc_lower == 'principal':
                total_principal += amt
                if rec.order_id and rec.order_id in order_dict:
                    order_dict[rec.order_id]['principal'] += amt
            elif 'tax' in desc_lower:
                total_product_tax += amt
                if rec.order_id and rec.order_id in order_dict:
                    order_dict[rec.order_id]['tax'] += amt
            elif amt < 0:
                abs_amt = abs(amt)
                total_amazon_fees += abs_amt
                if rec.order_id and rec.order_id in order_dict:
                    order_dict[rec.order_id]['fees'] += abs_amt
            elif amt > 0:
                total_principal += amt
                if rec.order_id and rec.order_id in order_dict:
                    order_dict[rec.order_id]['principal'] += amt

        # Bulk fallback lookup for created accounting documents
        order_ids_list = list(distinct_orders)
        if order_ids_list:
            entries = self.env['account.move'].search([
                ('amazon_order_id', 'in', order_ids_list),
                ('move_type', '=', 'entry')
            ])
            entries_by_order = {e.amazon_order_id: e for e in entries}

            bills = self.env['account.move'].search([
                ('amazon_order_id', 'in', order_ids_list),
                ('move_type', '=', 'in_invoice')
            ])
            bills_by_order = {b.amazon_order_id: b for b in bills}

            invoices = self.env['account.move'].search([
                ('amazon_order_id', 'in', order_ids_list),
                ('move_type', '=', 'out_invoice')
            ])
            invoices_by_order = {i.amazon_order_id: i for i in invoices}

            for oid, odata in order_dict.items():
                if not odata.get('move_id') and oid in entries_by_order:
                    ent = entries_by_order[oid]
                    odata['move_id'] = ent.id
                    odata['move_name'] = ent.name or f"Entry #{ent.id}"

                if not odata.get('vendor_bill_id') and oid in bills_by_order:
                    bll = bills_by_order[oid]
                    odata['vendor_bill_id'] = bll.id
                    odata['vendor_bill_name'] = bll.name or f"Bill #{bll.id}"

                if not odata.get('payment_id'):
                    if oid in invoices_by_order and invoices_by_order[oid].payment_ids:
                        pmt = invoices_by_order[oid].payment_ids[0]
                        odata['payment_id'] = pmt.id
                        odata['payment_name'] = pmt.name or f"Payment #{pmt.id}"
                    else:
                        pmt = self.env['account.payment'].search(['|', ('memo', 'ilike', oid), ('payment_reference', 'ilike', oid)], limit=1)
                        if pmt:
                            odata['payment_id'] = pmt.id
                            odata['payment_name'] = pmt.name or f"Payment #{pmt.id}"

                # Resolve payment move_id (Payment Journal Entry) if missing
                if odata.get('payment_id') and not odata.get('move_id'):
                    pmt_obj = self.env['account.payment'].browse(odata['payment_id'])
                    if pmt_obj and pmt_obj.move_id:
                        odata['move_id'] = pmt_obj.move_id.id
                        odata['move_name'] = pmt_obj.move_id.name or f"Entry #{pmt_obj.move_id.id}"

                # Mark order as processed only if at least one document exists
                odata['is_processed'] = bool(odata.get('payment_id') or odata.get('move_id') or odata.get('vendor_bill_id'))

        # Format orders list
        orders_list = []
        for oid, odata in order_dict.items():
            descs_list = [{'description': d, 'amount': round(a, 2)} for d, a in odata['descriptions'].items()]
            # Sort descriptions like Excel image (Principal first, fees, taxes, grand total)
            descs_list.sort(key=lambda x: (0 if x['description'].lower() == 'principal' else (1 if 'tax' in x['description'].lower() else 2), x['description']))
            
            p_amt = round(odata['principal'], 2)
            t_amt = round(odata['tax'], 2)
            f_amt = round(odata['fees'], 2)
            net_payout = round((p_amt + t_amt) - f_amt, 2)

            orders_list.append({
                'order_id': odata['order_id'],
                'posted_date': odata['posted_date'],
                'total_amount': net_payout,
                'principal': p_amt,
                'fees': f_amt,
                'tax': t_amt,
                'records_count': odata['records_count'],
                'is_processed': odata.get('is_processed', False),
                'payment_id': odata.get('payment_id', False),
                'payment_name': odata.get('payment_name', ''),
                'move_id': odata.get('move_id', False),
                'move_name': odata.get('move_name', ''),
                'vendor_bill_id': odata.get('vendor_bill_id', False),
                'vendor_bill_name': odata.get('vendor_bill_name', ''),
                'breakdown': descs_list,
            })

        orders_list.sort(key=lambda x: x['posted_date'] or '', reverse=True)

        # Selected order details
        selected_order_data = None
        if selected_order_id and selected_order_id in order_dict:
            selected_order_data = order_dict[selected_order_id]
        elif orders_list:
            selected_order_data = order_dict[orders_list[0]['order_id']]

        if selected_order_data:
            descs_list = [{'description': d, 'amount': round(a, 2)} for d, a in selected_order_data['descriptions'].items()]
            descs_list.sort(key=lambda x: (0 if x['description'].lower() == 'principal' else (1 if 'tax' in x['description'].lower() else 2), x['description']))
            
            p_amt = round(selected_order_data['principal'], 2)
            t_amt = round(selected_order_data['tax'], 2)
            f_amt = round(selected_order_data['fees'], 2)
            net_payout = round((p_amt + t_amt) - f_amt, 2)

            selected_order_data = {
                'order_id': selected_order_data['order_id'],
                'posted_date': selected_order_data['posted_date'],
                'total_amount': net_payout,
                'principal': p_amt,
                'fees': f_amt,
                'tax': t_amt,
                'records_count': selected_order_data['records_count'],
                'is_processed': selected_order_data.get('is_processed', False),
                'payment_id': selected_order_data.get('payment_id', False),
                'payment_name': selected_order_data.get('payment_name', ''),
                'move_id': selected_order_data.get('move_id', False),
                'move_name': selected_order_data.get('move_name', ''),
                'vendor_bill_id': selected_order_data.get('vendor_bill_id', False),
                'vendor_bill_name': selected_order_data.get('vendor_bill_name', ''),
                'breakdown': descs_list,
            }

        currency_symbol = self.env.company.currency_id.symbol or '₹'

        # Format field_totals list for UI KPI Cards
        field_totals = [
            {'description': d, 'amount': round(a, 2)}
            for d, a in field_totals_dict.items()
        ]
        field_totals.sort(key=lambda x: (0 if x['description'].lower() == 'principal' else 1, x['description']))

        total_payout_kpi = round((total_principal + total_product_tax) - total_amazon_fees, 2)

        return {
            'kpis': {
                'total_payout': total_payout_kpi,
                'total_principal': round(total_principal, 2),
                'total_product_tax': round(total_product_tax, 2),
                'total_amazon_fees': round(total_amazon_fees, 2),
                'total_withheld_taxes': round(total_withheld_taxes, 2),
                'total_orders_count': len(distinct_orders),
                'total_records_count': len(records),
                'currency_symbol': currency_symbol,
                'latest_batch_id': latest_batch,
                'field_totals': field_totals,
            },
            'orders': orders_list,
            'selected_order': selected_order_data,
            'all_order_ids': sorted(list(all_order_ids)),
        }

    @api.model
    def action_process_full_settlement_reconciliation(self, target_order_id=None):
        """ Automated Accounting Reconciliation for Amazon Settlement:
            1. Customer Payment Registration against Customer Invoice
            2. Segregation of Amazon Fee Deductions line-by-line per amount_description
               in Amazon Settlement Clearing Account (1221 / Clearing Account)
        """
        order_id = target_order_id
        if not order_id and isinstance(self, models.Model) and len(self) > 0:
            order_id = getattr(self[0], 'order_id', False)

        if not order_id:
            raise UserError(_("No Amazon Order ID provided for reconciliation."))

        # 1. Check for posted Customer Invoice
        invoice = self.env['account.move'].search([
            ('amazon_order_id', '=', order_id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted')
        ], limit=1)

        if not invoice:
            raise UserError(_("No posted Customer Invoice found for Amazon Order ID '%s'. Please create and post the Sale Order / Invoice first.") % order_id)

        # 2. Fetch Settlement Records for Order ID
        records = self.search([('order_id', '=', order_id)])
        if not records:
            raise UserError(_("No payment settlement records found for Order ID '%s'.") % order_id)

        # Calculate Gross Sales (Item Price: Principal + Tax, excluding TDS/TCS) and Amazon Fee Deductions
        gross_sales_amount = 0.0
        fee_total_amount = 0.0
        fee_breakdown = {}

        for rec in records:
            amt = rec.amount or 0.0
            desc = (rec.amount_description or rec.amount_type or 'Other Fee').strip()
            desc_lower = desc.lower()

            # Exclude TDS / TCS from Gross Sales Receipts & Fee calculations (Item Price already includes item TDS/TCS)
            if any(k in desc_lower for k in ['tcs', 'tds']):
                continue

            if amt > 0:
                gross_sales_amount += amt
            else:
                abs_amt = abs(amt)
                fee_total_amount += abs_amt
                fee_breakdown[desc] = fee_breakdown.get(desc, 0.0) + abs_amt

        # Round amounts
        gross_sales_amount = round(gross_sales_amount, 2)
        fee_total_amount = round(fee_total_amount, 2)
        net_settlement_payout = round(gross_sales_amount - fee_total_amount, 2)

        # Fallback account & partner lookups
        clearing_account = self.env.ref('amazon_sales_dashboard.account_amazon_clearing', raise_if_not_found=False)
        if not clearing_account:
            clearing_account = self.env['account.account'].search([('code', '=', '1221')], limit=1)
        if not clearing_account:
            clearing_account = self.env['account.account'].search([('name', 'ilike', 'Amazone')], limit=1)
        if not clearing_account:
            clearing_account = self.env['account.account'].search([('name', 'ilike', 'Amazon Settlement Clearing')], limit=1)
        if not clearing_account:
            clearing_account = self.env['account.account'].search([('account_type', 'in', ['asset_current', 'liability_current'])], limit=1)
    
        amazon_partner = self.env.ref('amazon_sales_dashboard.partner_amazon_vendor', raise_if_not_found=False)
        if not amazon_partner:
            amazon_partner = self.env['res.partner'].search([('name', 'ilike', 'Amazon')], limit=1)
        if not amazon_partner:
            amazon_partner = self.env['res.partner'].create({
                'name': 'Amazon Sellers',
                'supplier_rank': 1,
                'is_company': True,
            })

        payment_journal = self.env['account.journal'].search([('type', 'in', ['bank', 'cash'])], limit=1)

        # STEP 1: Customer Invoice Payment Registration + Write-Off
        payment = False
        receivable_line = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        
        # Check if invoice already has payments linked
        existing_payments = invoice.payment_ids or (invoice._get_reconciled_payments() if hasattr(invoice, '_get_reconciled_payments') else False)
        if existing_payments:
            payment = existing_payments[0]
        elif invoice.amount_residual > 0 and receivable_line:
            if fee_total_amount > 0 and clearing_account:
                pay_amount = max(0.0, round(invoice.amount_residual - fee_total_amount, 2))
                if net_settlement_payout > 0:
                    pay_amount = net_settlement_payout
                diff_amount = fee_total_amount
            else:
                pay_amount = min(net_settlement_payout if net_settlement_payout > 0 else gross_sales_amount, invoice.amount_residual)
                diff_amount = 0.0

            pay_wizard_vals = {
                'amount': pay_amount,
                'payment_date': invoice.invoice_date or fields.Date.today(),
                'journal_id': payment_journal.id if payment_journal else False,
                'communication': f"Amazon Payout - {order_id}",
            }

            if diff_amount > 0 and clearing_account:
                pay_wizard_vals.update({
                    'payment_difference_handling': 'reconcile',
                    'writeoff_account_id': clearing_account.id,
                    'writeoff_label': f"Amazon Fee Deductions - {order_id}",
                })

            pay_wizard = self.env['account.payment.register'].with_context(
                active_model='account.move',
                active_ids=invoice.ids
            ).create(pay_wizard_vals)
            
            res_pay = pay_wizard.action_create_payments()
            if res_pay and isinstance(res_pay, dict) and res_pay.get('res_id'):
                payment = self.env['account.payment'].browse(res_pay['res_id'])
            else:
                pmts = invoice.payment_ids or (invoice._get_reconciled_payments() if hasattr(invoice, '_get_reconciled_payments') else False)
                if pmts:
                    payment = pmts[0]
                else:
                    payment = self.env['account.payment'].search([
                        '|', ('memo', 'ilike', order_id), ('payment_reference', 'ilike', order_id)
                    ], order='id desc', limit=1)

        if not payment:
            # Fallback search for any existing payment for order_id
            payment = self.env['account.payment'].search([
                '|', ('memo', 'ilike', order_id), ('payment_reference', 'ilike', order_id)
            ], order='id desc', limit=1)

        if not payment:
            raise UserError(_("Could not register or locate Payment for Customer Invoice '%s' (Order ID '%s').") % (invoice.name, order_id))

        # STEP 2: Segregate Write-Off lines on payment.move_id per fee description
        if payment and payment.move_id:
            move = payment.move_id
            if fee_breakdown and clearing_account:
                writeoff_lines = move.line_ids.filtered(lambda l: l.account_id.id == clearing_account.id)
                if writeoff_lines:
                    move.button_draft()
                    line_commands = []
                    # Keep non-clearing lines (bank liquidity line & customer receivable line)
                    for line in move.line_ids:
                        if line.account_id.id != clearing_account.id:
                            line_commands.append((4, line.id, 0))
                        else:
                            line_commands.append((2, line.id, 0))
                    
                    # Add segregated fee lines for each description in fee_breakdown
                    for fee_desc, fee_amt in fee_breakdown.items():
                        fee_amt_rounded = round(fee_amt, 2)
                        if fee_amt_rounded <= 0:
                            continue
                        
                        fee_label = f"Amazon {fee_desc} - {order_id}"
                        line_commands.append((0, 0, {
                            'account_id': clearing_account.id,
                            'partner_id': amazon_partner.id if amazon_partner else invoice.partner_id.id,
                            'name': fee_label,
                            'debit': fee_amt_rounded,
                            'credit': 0.0,
                            'currency_id': move.currency_id.id or self.env.company.currency_id.id,
                        }))
                    
                    move.write({'line_ids': line_commands})
                    move.action_post()
                    
                    # Ensure invoice receivable line remains reconciled with payment receivable line
                    inv_rec = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)
                    pmt_rec = move.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)
                    if inv_rec and pmt_rec:
                        (inv_rec + pmt_rec).reconcile()

            if 'amazon_order_id' in move._fields:
                move.write({'amazon_order_id': order_id})

        # Update records status
        records.write({
            'state': 'posted',
            'payment_id': payment.id if payment else False,
            'move_id': payment.move_id.id if (payment and payment.move_id) else False,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Settlement Reconciliation Complete"),
                'message': _("Successfully reconciled Customer Payment %s with segregated Amazon fee lines for Order %s.") % (
                    payment.name if payment else '',
                    order_id
                ),
                'type': 'success',
                'sticky': True,
            }
        }

    def action_create_journal_entry(self):
        """ Redirect to automated reconciliation process """
        order_id = self[0].order_id if self else False
        return self.action_process_full_settlement_reconciliation(order_id)

    def action_create_payment(self):
        """ Redirect to automated reconciliation process """
        order_id = self[0].order_id if self else False
        return self.action_process_full_settlement_reconciliation(order_id)

