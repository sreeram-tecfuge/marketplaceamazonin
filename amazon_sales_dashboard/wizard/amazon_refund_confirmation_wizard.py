# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AmazonRefundConfirmationWizard(models.TransientModel):
    _name = 'amazon.refund.confirmation.wizard'
    _description = 'Amazon Refund Confirmation Wizard'

    record_id = fields.Many2one('amazon.dashboard.record', string="Dashboard Record", required=True)
    shipment_record_id = fields.Many2one('amazon.dashboard.record', string="Shipment Record")
    wizard_type = fields.Selection([
        ('so_pending', 'Sale Order Pending'),
        ('no_so_found', 'No Sale Order Found')
    ], string="Wizard Type", required=True)

    message = fields.Text(string="Confirmation Message", readonly=True)

    def action_create_so_then_refund(self):
        """ Creates Sale Order for the shipment first, then creates the linked refund """
        self.ensure_one()
        if self.shipment_record_id and self.shipment_record_id.state != 'so_created':
            self.shipment_record_id.action_create_sale_order()
        return self.record_id.action_create_refund(force_direct=True)

    def action_create_direct_refund(self):
        """ Directly creates Credit Note without linked Sale Order """
        self.ensure_one()
        return self.record_id.action_create_refund(force_direct=True)
