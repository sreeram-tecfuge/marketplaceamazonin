# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    asin = fields.Char(string="ASIN", help="Amazon Standard Identification Number")
    product_tax_code = fields.Char(string="Product Tax Code", help="Amazon Product Tax Code (e.g. A_GEN_STANDARD)")


class ProductProduct(models.Model):
    _inherit = 'product.product'

    asin = fields.Char(related='product_tmpl_id.asin', inherited=True, readonly=False)
    product_tax_code = fields.Char(related='product_tmpl_id.product_tax_code', inherited=True, readonly=False)
