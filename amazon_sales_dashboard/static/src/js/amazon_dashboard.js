/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AmazonSalesDashboard extends Component {
    static template = "amazon_sales_dashboard.AmazonDashboardTemplate";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            kpis: {},
            allRecords: [],
            filteredRecords: [],
            typeFilter: "All", // 'All', 'Shipment', 'Refund'
            statusFilter: "pending", // 'pending' (default), 'all', 'so_created', 'refund_created', 'error'
            searchQuery: "",
            selectedIds: new Set(),
            isAllSelected: false,
            isLoading: false,
            isCleared: false,
            isAllDashboard: false,
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        this.state.isLoading = true;
        this.state.isCleared = false;
        try {
            const data = await this.orm.call("amazon.dashboard.record", "get_dashboard_data", [this.state.isAllDashboard]);
            this.state.kpis = data.kpis || {};
            this.state.allRecords = data.all_records || [];
            this.state.selectedIds.clear();
            this.state.isAllSelected = false;
            this.applyFilters();
        } catch (error) {
            console.error("Error loading Amazon dashboard data:", error);
            if (this.notification) {
                this.notification.add("Failed to load Amazon Dashboard Data", { type: "danger" });
            }
        } finally {
            this.state.isLoading = false;
        }
    }

    applyFilters() {
        let result = [...this.state.allRecords];

        // 1. Transaction Type Filter
        if (this.state.typeFilter !== "All") {
            result = result.filter(r => r.transaction_type === this.state.typeFilter);
        }

        // 2. Status Filter
        if (this.state.statusFilter === "pending") {
            result = result.filter(r => r.state === "draft" || r.state === "error");
        } else if (this.state.statusFilter === "so_created") {
            result = result.filter(r => r.state === "so_created");
        } else if (this.state.statusFilter === "refund_created") {
            result = result.filter(r => r.state === "refund_created");
        } else if (this.state.statusFilter === "cancelled") {
            result = result.filter(r => r.state === "cancelled");
        } else if (this.state.statusFilter === "replacement_created") {
            result = result.filter(r => r.state === "replacement_created");
        } else if (this.state.statusFilter === "error") {
            result = result.filter(r => r.state === "error");
        }

        // 3. Search Query Filter
        const q = (this.state.searchQuery || "").toLowerCase().trim();
        if (q) {
            result = result.filter(r =>
                r.order_id.toLowerCase().includes(q) ||
                r.invoice_number.toLowerCase().includes(q) ||
                r.credit_note_no.toLowerCase().includes(q) ||
                r.sku.toLowerCase().includes(q) ||
                r.ship_to.toLowerCase().includes(q)
            );
        }

        this.state.filteredRecords = result;
        this.updateSelectAllStatus();
    }

    onSelectKpiCard(type, status) {
        this.state.typeFilter = type;
        this.state.statusFilter = status;
        this.applyFilters();
    }

    onTypeFilterChange(type) {
        this.state.typeFilter = type;
        if (type === "Shipment" && this.state.statusFilter === "refund_created") {
            this.state.statusFilter = "pending";
        } else if (type === "Refund" && this.state.statusFilter === "so_created") {
            this.state.statusFilter = "pending";
        }
        this.applyFilters();
    }

    onStatusFilterChange(ev) {
        this.state.statusFilter = ev.target.value;
        this.applyFilters();
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        this.applyFilters();
    }

    onClearDashboardView() {
        this.state.allRecords = [];
        this.state.filteredRecords = [];
        this.state.kpis = {
            total_shipments_count: 0,
            total_shipment_amount: 0,
            pending_shipments_count: 0,
            total_refunds_count: 0,
            total_refund_amount: 0,
            pending_refunds_count: 0,
            currency_symbol: this.state.kpis.currency_symbol || '₹',
            latest_batch_id: "Dashboard Cleared",
        };
        this.state.selectedIds.clear();
        this.state.isAllSelected = false;
        this.state.isCleared = true;
        this.notification.add("Dashboard view cleared. (Database records remain safe)", { type: "info" });
    }

    toggleSelectAll(ev) {
        const checked = ev.target.checked;
        this.state.isAllSelected = checked;
        if (checked) {
            for (const r of this.state.filteredRecords) {
                this.state.selectedIds.add(r.id);
            }
        } else {
            this.state.selectedIds.clear();
        }
    }

    toggleSelectRecord(recordId) {
        if (this.state.selectedIds.has(recordId)) {
            this.state.selectedIds.delete(recordId);
        } else {
            this.state.selectedIds.add(recordId);
        }
        this.updateSelectAllStatus();
    }

    updateSelectAllStatus() {
        if (this.state.filteredRecords.length === 0) {
            this.state.isAllSelected = false;
            return;
        }
        this.state.isAllSelected = this.state.filteredRecords.every(r => this.state.selectedIds.has(r.id));
    }

    async onProcessSelected() {
        const selectedArray = Array.from(this.state.selectedIds);
        if (selectedArray.length === 0) {
            this.notification.add("Please select at least one record to process.", { type: "warning" });
            return;
        }

        this.state.isLoading = true;
        try {
            await this.orm.call("amazon.dashboard.record", "action_process_selected", [selectedArray]);
            this.notification.add(`Processed ${selectedArray.length} selected record(s) successfully!`, { type: "success" });
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error processing selected records:", error);
            const msg = error.data && error.data.message ? error.data.message : (error.message || String(error));
            this.notification.add(`Error processing records: ${msg}`, { type: "danger", sticky: true });
            await this.loadDashboardData();
        }
    }

    async onUploadCsv() {
        await this.action.doAction("amazon_sales_dashboard.action_amazon_csv_import_wizard", {
            onClose: async () => {
                await this.loadDashboardData();
            }
        });
    }

    async onCreateSaleOrder(recordId) {
        try {
            const res = await this.orm.call("amazon.dashboard.record", "action_create_sale_order", [[recordId]]);
            const soName = res && res.name ? res.name : "Sale Order";
            const soId = res && res.res_id ? res.res_id : false;

            if (soId) {
                this.notification.add(`Sale Order ${soName}, Delivery & Invoice generated successfully!`, {
                    type: "success",
                    buttons: [{
                        name: `Open ${soName}`,
                        onClick: () => {
                            this.action.doAction({
                                type: "ir.actions.act_window",
                                res_model: "sale.order",
                                res_id: soId,
                                views: [[false, "form"]],
                                target: "current",
                            });
                        }
                    }]
                });
            } else {
                this.notification.add("Sale Order, Delivery & Invoice generated successfully!", { type: "success" });
            }
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error creating Sale Order:", error);
            const msg = error.data && error.data.message ? error.data.message : (error.message || String(error));
            this.notification.add(`Error creating Sale Order: ${msg}`, { type: "danger", sticky: true });
            await this.loadDashboardData();
        }
    }

    async onCreateRefund(recordId) {
        try {
            const res = await this.orm.call("amazon.dashboard.record", "action_create_refund", [[recordId]]);
            if (res && typeof res === 'object' && res.type === 'ir.actions.act_window') {
                await this.action.doAction(res, {
                    onClose: async () => {
                        await this.loadDashboardData();
                    }
                });
                return;
            }
            const cnName = res && res.name ? res.name : "Credit Note";
            const cnId = res && res.res_id ? res.res_id : false;

            if (cnId) {
                this.notification.add(`Refund Credit Note ${cnName} generated successfully!`, {
                    type: "success",
                    buttons: [{
                        name: `Open ${cnName}`,
                        onClick: () => {
                            this.action.doAction({
                                type: "ir.actions.act_window",
                                res_model: "account.move",
                                res_id: cnId,
                                views: [[false, "form"]],
                                target: "current",
                            });
                        }
                    }]
                });
            } else {
                this.notification.add("Refund (Credit Note) generated successfully!", { type: "success" });
            }
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error creating Refund:", error);
            const msg = error.data && error.data.message ? error.data.message : (error.message || String(error));
            this.notification.add(`Error creating Refund: ${msg}`, { type: "danger", sticky: true });
            await this.loadDashboardData();
        }
    }

    async onProcessCancel(recordId) {
        try {
            const res = await this.orm.call("amazon.dashboard.record", "action_process_cancel", [[recordId]]);
            if (res && typeof res === 'object' && res.type === 'ir.actions.act_window') {
                await this.action.doAction(res, {
                    onClose: async () => {
                        await this.loadDashboardData();
                    }
                });
                return;
            }
            const docName = res && res.name ? res.name : "Cancelled Order";
            const soId = res && res.res_id ? res.res_id : false;

            if (soId) {
                this.notification.add(`Order ${docName} cancelled successfully! Return delivery generated & invoice reversed.`, {
                    type: "success",
                    buttons: [{
                        name: `Open ${docName}`,
                        onClick: () => {
                            this.action.doAction({
                                type: "ir.actions.act_window",
                                res_model: "sale.order",
                                res_id: soId,
                                views: [[false, "form"]],
                                target: "current",
                            });
                        }
                    }]
                });
            } else {
                this.notification.add("Order cancellation processed successfully!", { type: "success" });
            }
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error processing Cancel:", error);
            const msg = error.data && error.data.message ? error.data.message : (error.message || String(error));
            this.notification.add(`Error processing Cancel: ${msg}`, { type: "danger", sticky: true });
            await this.loadDashboardData();
        }
    }

    async onCreateFreeReplacement(recordId) {
        try {
            const res = await this.orm.call("amazon.dashboard.record", "action_create_free_replacement", [[recordId]]);
            if (res && typeof res === 'object' && res.type === 'ir.actions.act_window') {
                await this.action.doAction(res, {
                    onClose: async () => {
                        await this.loadDashboardData();
                    }
                });
                return;
            }
            const soName = res && res.name ? res.name : "Replacement Order";
            const soId = res && res.res_id ? res.res_id : false;

            if (soId) {
                this.notification.add(`Free Replacement Order ${soName} & Delivery generated successfully!`, {
                    type: "success",
                    buttons: [{
                        name: `Open ${soName}`,
                        onClick: () => {
                            this.action.doAction({
                                type: "ir.actions.act_window",
                                res_model: "sale.order",
                                res_id: soId,
                                views: [[false, "form"]],
                                target: "current",
                            });
                        }
                    }]
                });
            } else {
                this.notification.add("Free Replacement Order generated successfully!", { type: "success" });
            }
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error creating Free Replacement:", error);
            const msg = error.data && error.data.message ? error.data.message : (error.message || String(error));
            this.notification.add(`Error creating Free Replacement: ${msg}`, { type: "danger", sticky: true });
            await this.loadDashboardData();
        }
    }

    async onInspectRecord(recordId) {
        await this.action.doAction({
            name: "Amazon Transaction Details",
            type: "ir.actions.act_window",
            res_model: "amazon.dashboard.record",
            res_id: recordId,
            views: [[false, "form"]],
            target: "new",
        });
    }

    async onRefresh() {
        await this.loadDashboardData();
    }
}

export class AmazonAllSalesDashboard extends AmazonSalesDashboard {
    setup() {
        super.setup();
        this.state.isAllDashboard = true;
    }
}

registry.category("actions").add("amazon_dashboard_main_action", AmazonSalesDashboard);
registry.category("actions").add("amazon_dashboard_all_action", AmazonAllSalesDashboard);
