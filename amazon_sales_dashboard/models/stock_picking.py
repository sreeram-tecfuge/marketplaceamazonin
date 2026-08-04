# -*- coding: utf-8 -*-
from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    amazon_shipment_id = fields.Char(string="Amazon Shipment ID")


class StockMove(models.Model):
    _inherit = 'stock.move'

    amazon_shipment_item_id = fields.Char(string="Amazon Shipment Item ID", help="Shipment item ID from Amazon CSV")
