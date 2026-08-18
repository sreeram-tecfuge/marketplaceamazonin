# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    asin = fields.Char(string="ASIN", help="Amazon Standard Identification Number")
    product_tax_code = fields.Char(string="Product Tax Code", help="Amazon Product Tax Code (e.g. A_GEN_STANDARD)")
    is_amazon_settlement_fee = fields.Boolean(
        string="Is Amazon Settlement Fee",
        default=False,
        help="Identifies service products automatically created during Amazon Payment Settlement reconciliation."
    )

    def write(self, vals):
        if 'name' in vals:
            for product in self:
                if product.is_amazon_settlement_fee and vals['name'] != product.name:
                    raise UserError(_("You cannot modify the name of an Amazon Settlement Fee product ('%s').") % product.name)
        return super(ProductTemplate, self).write(vals)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    asin = fields.Char(related='product_tmpl_id.asin', inherited=True, readonly=False)
    product_tax_code = fields.Char(related='product_tmpl_id.product_tax_code', inherited=True, readonly=False)
    is_amazon_settlement_fee = fields.Boolean(related='product_tmpl_id.is_amazon_settlement_fee', inherited=True, readonly=False)

    def write(self, vals):
        if 'name' in vals:
            for product in self:
                if product.is_amazon_settlement_fee and vals['name'] != product.name:
                    raise UserError(_("You cannot modify the name of an Amazon Settlement Fee product ('%s').") % product.name)
        return super(ProductProduct, self).write(vals)
