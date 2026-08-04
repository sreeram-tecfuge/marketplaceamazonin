# -*- coding: utf-8 -*-
from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    amazon_order_id = fields.Char(string="Amazon Order ID", index=True, help="Amazon Sales Order ID")
    amazon_shipment_id = fields.Char(string="Amazon Shipment ID", help="Amazon Shipment ID mapped to Source Document")
