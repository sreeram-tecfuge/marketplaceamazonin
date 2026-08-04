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
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        this.state.isLoading = true;
        try {
            const data = await this.orm.call("amazon.dashboard.record", "get_dashboard_data", []);
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

        // 2. Status Filter (Default: 'pending' -> draft & error)
        if (this.state.statusFilter === "pending") {
            result = result.filter(r => r.state === "draft" || r.state === "error");
        } else if (this.state.statusFilter === "so_created") {
            result = result.filter(r => r.state === "so_created");
        } else if (this.state.statusFilter === "refund_created") {
            result = result.filter(r => r.state === "refund_created");
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
            await this.orm.call("amazon.dashboard.record", "action_create_sale_order", [[recordId]]);
            this.notification.add("Sale Order, Delivery & Invoice generated successfully!", { type: "success" });
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
            await this.orm.call("amazon.dashboard.record", "action_create_refund", [[recordId]]);
            this.notification.add("Refund (Credit Note) generated successfully!", { type: "success" });
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error creating Refund:", error);
            const msg = error.data && error.data.message ? error.data.message : (error.message || String(error));
            this.notification.add(`Error creating Refund: ${msg}`, { type: "danger", sticky: true });
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

registry.category("actions").add("amazon_dashboard_main_action", AmazonSalesDashboard);
