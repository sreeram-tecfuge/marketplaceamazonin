# -*- coding: utf-8 -*-
{
    'name': 'Amazon Sales Dashboard',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Amazon CSV/Excel Upload, Dynamic JS Dashboard & Automated Sale/Delivery/Invoice/Refund Workflow',
    'description': """
Amazon Sales Dashboard
======================
- Dynamic JS/OWL Amazon Dashboard.
- Upload daily, weekly, or monthly Amazon CSV/Excel transaction files.
- Persistent historical records stored in Amazon Dashboard Records.
- Filtered to Shipment and Refund transaction types.
- Two-section Dashboard view for Shipment Data and Refund Data.
- Single and Bulk actions:
  - Create Sale Order + Delivery + Invoice for Shipments.
  - Create & Link Refund (Credit Note) for Refunds against existing Sale Orders or standalone.
- Auto mapping of ASIN, Product Tax Code, HSN/SAC, Shipment Item ID, GST Taxes.
    """,
    'author': 'Antigravity AI',
    'website': 'https://example.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale_management',
        'stock',
        'account',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/stock_picking_views.xml',
        'wizard/amazon_csv_import_wizard_views.xml',
        'views/amazon_dashboard_record_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'amazon_sales_dashboard/static/src/scss/amazon_dashboard.scss',
            'amazon_sales_dashboard/static/src/js/amazon_dashboard.js',
            'amazon_sales_dashboard/static/src/xml/amazon_dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
