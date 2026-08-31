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
            showBreakdownModal: false,
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
        const found = this.state.orders.find(o => o.order_id === orderId);
        if (found) {
            this.state.selectedOrder = found;
        } else {
            await this.loadDashboardData(orderId);
        }
    }

    async onOpenBreakdownWizard(orderId) {
        if (orderId) {
            await this.onSelectOrder(orderId);
        }
        this.state.showBreakdownModal = true;
    }

    onCloseBreakdownWizard() {
        this.state.showBreakdownModal = false;
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

    async onProcessFullSettlement(orderId) {
        const targetOrderId = orderId || (this.state.selectedOrder ? this.state.selectedOrder.order_id : null);
        if (!targetOrderId) {
            this.notification.add("Please select an Amazon Order ID to process.", { type: "warning" });
            return;
        }

        this.state.isLoading = true;
        try {
            const res = await this.orm.call(
                "amazon.payment.record",
                "action_process_full_settlement_reconciliation",
                [targetOrderId]
            );
            if (res && typeof res === "object" && res.type === "ir.actions.client") {
                await this.action.doAction(res);
            } else {
                this.notification.add(`Successfully processed Payment & Segregated Fee Clearing for Order ${targetOrderId}!`, { type: "success" });
            }
            await this.loadDashboardData(targetOrderId);
        } catch (error) {
            console.error("Error processing full settlement reconciliation:", error);
            const msg = error.data && error.data.message ? error.data.message : (error.message || String(error));
            this.notification.add(msg, { type: "danger", sticky: true });
        } finally {
            this.state.isLoading = false;
        }
    }

    async onCreateJournalEntry() {
        if (this.state.selectedOrder) {
            await this.onProcessFullSettlement(this.state.selectedOrder.order_id);
        }
    }

    async onCreatePayment() {
        if (this.state.selectedOrder) {
            await this.onProcessFullSettlement(this.state.selectedOrder.order_id);
        }
    }

    async onOpenPayment(paymentId) {
        if (!paymentId) return;
        await this.action.doAction({
            name: "Created Customer Payment",
            type: "ir.actions.act_window",
            res_model: "account.payment",
            res_id: paymentId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async onOpenJournalEntry(moveId) {
        if (!moveId) return;
        await this.action.doAction({
            name: "Created Transfer Journal Entry",
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: moveId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async onOpenVendorBill(billId) {
        if (!billId) return;
        await this.action.doAction({
            name: "Created Amazon Vendor Bill",
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: billId,
            views: [[false, "form"]],
            target: "current",
        });
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

    async onToggleAllDashboard() {
        this.state.isAllDashboard = !this.state.isAllDashboard;
        await this.loadDashboardData();
    }

    async onRefresh() {
        await this.loadDashboardData();
    }
}

export class AmazonAllPaymentDashboard extends AmazonPaymentDashboard {
    setup() {
        super.setup();
        this.state.isAllDashboard = true;
    }
}

registry.category("actions").add("amazon_payment_dashboard_action", AmazonPaymentDashboard);
registry.category("actions").add("amazon_payment_dashboard_all_action", AmazonAllPaymentDashboard);
