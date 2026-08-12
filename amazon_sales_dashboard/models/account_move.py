# -*- coding: utf-8 -*-
from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    amazon_invoice_number = fields.Char(string="Amazon Invoice Number", index=True)
    amazon_order_id = fields.Char(string="Amazon Order ID", index=True)
    amazon_shipment_id = fields.Char(string="Amazon Shipment ID", index=True)
    credit_note_no = fields.Char(string="Credit Note Number")
    credit_note_date = fields.Datetime(string="Credit Note Date")
    is_amazon_replacement = fields.Boolean(string="Is Amazon Replacement", copy=False)
