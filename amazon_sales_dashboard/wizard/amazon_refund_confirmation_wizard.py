# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AmazonRefundConfirmationWizard(models.TransientModel):
    _name = 'amazon.refund.confirmation.wizard'
    _description = 'Amazon Refund Confirmation Wizard'

    record_id = fields.Many2one('amazon.dashboard.record', string="Dashboard Record", required=True)
    shipment_record_id = fields.Many2one('amazon.dashboard.record', string="Shipment Record")
    transaction_type = fields.Selection(related='record_id.transaction_type', readonly=True)
    wizard_type = fields.Selection([
        ('so_pending', 'Sale Order Pending'),
        ('no_so_found', 'No Sale Order Found'),
        ('confirm_cancel', 'Confirm Cancellation'),
        ('confirm_replace', 'Confirm Replacement')
    ], string="Wizard Type", required=True)

    replacement_unit_price = fields.Float(string="Replacement Unit Price", default=0.0)
    replacement_ref = fields.Char(string="Order Reference / Note")
    currency_id = fields.Many2one('res.currency', related='record_id.currency_id', readonly=True)
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

    def action_create_so_then_cancel(self):
        """ Creates Sale Order for the shipment first, then processes cancel """
        self.ensure_one()
        if self.shipment_record_id and self.shipment_record_id.state != 'so_created':
            self.shipment_record_id.action_create_sale_order()
        return self.record_id.action_process_cancel(force_direct=True)

    def action_create_direct_cancel(self):
        """ Directly processes cancel without linked Sale Order """
        self.ensure_one()
        return self.record_id.action_process_cancel(force_direct=True)

    def action_create_so_then_replace(self):
        """ Creates standalone replacement order """
        self.ensure_one()
        return self.record_id.action_create_free_replacement(
            force_direct=True,
            replacement_unit_price=self.replacement_unit_price,
            replacement_ref=self.replacement_ref
        )

    def action_confirm_replace(self):
        """ Confirms creating replacement order """
        self.ensure_one()
        return self.record_id.action_create_free_replacement(
            force_direct=True,
            replacement_unit_price=self.replacement_unit_price,
            replacement_ref=self.replacement_ref
        )

    def action_confirm_cancel(self):
        """ Confirms cancellation of existing Sale Order """
        self.ensure_one()
        return self.record_id.action_process_cancel(force_direct=True)


