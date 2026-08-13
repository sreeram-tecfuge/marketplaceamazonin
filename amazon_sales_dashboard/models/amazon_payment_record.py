# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

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

        distinct_orders = set()
        order_dict = {}
        all_order_ids = set()

        for rec in records:
            amt = rec.amount or 0.0
            total_payout += amt
            desc = (rec.amount_description or '').strip()
            desc_lower = desc.lower()

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
                    }
                
                ord_info = order_dict[rec.order_id]
                ord_info['total_amount'] += amt
                ord_info['records_count'] += 1
                
                # Breakdown by description
                if desc not in ord_info['descriptions']:
                    ord_info['descriptions'][desc] = 0.0
                ord_info['descriptions'][desc] += amt

            # Categorize KPI amounts
            if desc_lower == 'principal' or rec.amount_type == 'ItemPrice':
                if desc_lower == 'principal':
                    total_principal += amt
                    if rec.order_id and rec.order_id in order_dict:
                        order_dict[rec.order_id]['principal'] += amt
                elif desc_lower == 'product tax' or 'tax' in desc_lower:
                    total_product_tax += amt
                    if rec.order_id and rec.order_id in order_dict:
                        order_dict[rec.order_id]['tax'] += amt

            if 'tax' in desc_lower and desc_lower != 'principal':
                if 'tcs' in desc_lower or 'tds' in desc_lower:
                    total_withheld_taxes += amt
                else:
                    total_product_tax += amt
                if rec.order_id and rec.order_id in order_dict:
                    order_dict[rec.order_id]['tax'] += amt
            
            if any(k in desc_lower for k in ['commission', 'fee', 'charges', 'postage', 'easyship', 'shipping']):
                total_amazon_fees += amt
                if rec.order_id and rec.order_id in order_dict:
                    order_dict[rec.order_id]['fees'] += amt

        # Format orders list
        orders_list = []
        for oid, odata in order_dict.items():
            descs_list = [{'description': d, 'amount': round(a, 2)} for d, a in odata['descriptions'].items()]
            # Sort descriptions like Excel image (Principal first, fees, taxes, grand total)
            descs_list.sort(key=lambda x: (0 if x['description'].lower() == 'principal' else (1 if 'tax' in x['description'].lower() else 2), x['description']))
            
            orders_list.append({
                'order_id': odata['order_id'],
                'posted_date': odata['posted_date'],
                'total_amount': round(odata['total_amount'], 2),
                'principal': round(odata['principal'], 2),
                'fees': round(odata['fees'], 2),
                'tax': round(odata['tax'], 2),
                'records_count': odata['records_count'],
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
            selected_order_data = {
                'order_id': selected_order_data['order_id'],
                'posted_date': selected_order_data['posted_date'],
                'total_amount': round(selected_order_data['total_amount'], 2),
                'principal': round(selected_order_data['principal'], 2),
                'fees': round(selected_order_data['fees'], 2),
                'tax': round(selected_order_data['tax'], 2),
                'records_count': selected_order_data['records_count'],
                'breakdown': descs_list,
            }

        currency_symbol = self.env.company.currency_id.symbol or '₹'

        return {
            'kpis': {
                'total_payout': round(total_payout, 2),
                'total_principal': round(total_principal, 2),
                'total_product_tax': round(total_product_tax, 2),
                'total_amazon_fees': round(total_amazon_fees, 2),
                'total_withheld_taxes': round(total_withheld_taxes, 2),
                'total_orders_count': len(distinct_orders),
                'total_records_count': len(records),
                'currency_symbol': currency_symbol,
                'latest_batch_id': latest_batch,
            },
            'orders': orders_list,
            'selected_order': selected_order_data,
            'all_order_ids': sorted(list(all_order_ids)),
        }

    def action_create_journal_entry(self):
        """ Hook for future Journal Entry creation """
        for rec in self:
            if rec.move_id:
                raise models.UserError(_("Journal entry already created for order %s.") % rec.order_id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Journal Entry Creation"),
                'message': _("Journal Entry creation logic is ready for integration in the next update."),
                'type': 'info',
                'sticky': False,
            }
        }

    def action_create_payment(self):
        """ Hook for future Payment creation """
        for rec in self:
            if rec.payment_id:
                raise models.UserError(_("Payment already registered for order %s.") % rec.order_id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Payment Registration"),
                'message': _("Payment registration logic is ready for integration in the next update."),
                'type': 'info',
                'sticky': False,
            }
        }
