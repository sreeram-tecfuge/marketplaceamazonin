/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AmazonPaymentDashboard extends Component {
    static template = "amazon_sales_dashboard.AmazonPaymentDashboardTemplate";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            kpis: {},
            orders: [],
            filteredOrders: [],
            allOrderIds: [],
            selectedOrder: null,
            selectedOrderId: "",
            searchQuery: "",
            isLoading: false,
            isAllDashboard: false,
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData(targetOrderId = null) {
        this.state.isLoading = true;
        try {
            const data = await this.orm.call(
                "amazon.payment.record",
                "get_payment_dashboard_data",
                [this.state.isAllDashboard, targetOrderId || this.state.selectedOrderId]
            );
            this.state.kpis = data.kpis || {};
            this.state.orders = data.orders || [];
            this.state.allOrderIds = data.all_order_ids || [];
            this.state.selectedOrder = data.selected_order || null;
            if (this.state.selectedOrder) {
                this.state.selectedOrderId = this.state.selectedOrder.order_id;
            }
            this.applyFilters();
        } catch (error) {
            console.error("Error loading Amazon Payment Dashboard data:", error);
            if (this.notification) {
                this.notification.add("Failed to load Amazon Payment Dashboard Data", { type: "danger" });
            }
        } finally {
            this.state.isLoading = false;
        }
    }

    applyFilters() {
        let result = [...this.state.orders];
        const q = (this.state.searchQuery || "").toLowerCase().trim();
        if (q) {
            result = result.filter(o => o.order_id.toLowerCase().includes(q));
        }
        this.state.filteredOrders = result;
    }

    async onSelectOrder(orderId) {
        this.state.selectedOrderId = orderId;
        await this.loadDashboardData(orderId);
    }

    onOrderSelectChange(ev) {
        const val = ev.target.value;
        if (val) {
            this.onSelectOrder(val);
        }
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        this.applyFilters();
    }

    async onUploadPaymentCsv() {
        await this.action.doAction("amazon_sales_dashboard.action_amazon_payment_import_wizard", {
            onClose: async () => {
                await this.loadDashboardData();
            }
        });
    }

    async onCreateJournalEntry() {
        if (!this.state.selectedOrder) {
            this.notification.add("Please select an order first.", { type: "warning" });
            return;
        }
        try {
            const records = await this.orm.searchRead(
                "amazon.payment.record",
                [["order_id", "=", this.state.selectedOrder.order_id]],
                ["id"]
            );
            const ids = records.map(r => r.id);
            if (ids.length > 0) {
                const res = await this.orm.call("amazon.payment.record", "action_create_journal_entry", [ids]);
                await this.action.doAction(res);
            }
        } catch (error) {
            console.error("Error creating journal entry:", error);
        }
    }

    async onCreatePayment() {
        if (!this.state.selectedOrder) {
            this.notification.add("Please select an order first.", { type: "warning" });
            return;
        }
        try {
            const records = await this.orm.searchRead(
                "amazon.payment.record",
                [["order_id", "=", this.state.selectedOrder.order_id]],
                ["id"]
            );
            const ids = records.map(r => r.id);
            if (ids.length > 0) {
                const res = await this.orm.call("amazon.payment.record", "action_create_payment", [ids]);
                await this.action.doAction(res);
            }
        } catch (error) {
            console.error("Error creating payment:", error);
        }
    }

    async onInspectOrder(orderId) {
        await this.action.doAction({
            name: `Payment Records for Order ${orderId}`,
            type: "ir.actions.act_window",
            res_model: "amazon.payment.record",
            domain: [["order_id", "=", orderId]],
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    async onRefresh() {
        await this.loadDashboardData();
    }
}

registry.category("actions").add("amazon_payment_dashboard_action", AmazonPaymentDashboard);
