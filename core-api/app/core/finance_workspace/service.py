"""Canonical Finance workspace service."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from typing import TypeVar
from uuid import UUID

from app.core.analytics.engine import BusinessAnalyticsEngine, _build_period_window
from app.core.analytics.models import (
    AnalyticsDataQualityReport,
    AnalyticsDataStatus,
    AnalyticsMetricValue,
    AnalyticsQuery,
)
from app.core.data_layer.canonical_v2 import (
    CanonicalCustomerReturn,
    CanonicalCustomerReturnItem,
    CanonicalDataQualityStatus,
    CanonicalFinancialAccount,
    CanonicalFinancialDirection,
    CanonicalFinancialOperation,
    CanonicalOrganization,
    CanonicalPayment,
    CanonicalPaymentAllocation,
    CanonicalPurchase,
    CanonicalSupplierReturn,
    CanonicalWriteoff,
)
from app.core.data_layer.contracts import CoreDataStore
from app.core.finance_workspace.models import (
    FinanceWorkspaceAccountRow,
    FinanceWorkspaceCapabilityStatus,
    FinanceWorkspaceCoverageItem,
    FinanceWorkspaceDirection,
    FinanceWorkspaceFilterOption,
    FinanceWorkspaceFiltersMetadata,
    FinanceWorkspaceOperationRow,
    FinanceWorkspaceOverviewRow,
    FinanceWorkspacePagination,
    FinanceWorkspacePaymentRow,
    FinanceWorkspaceProvenance,
    FinanceWorkspaceQuery,
    FinanceWorkspaceResponse,
    FinanceWorkspaceReturnRow,
    FinanceWorkspaceRows,
    FinanceWorkspaceSortBy,
    FinanceWorkspaceSortOrder,
    FinanceWorkspaceSummary,
    FinanceWorkspaceTabStatus,
    FinanceWorkspaceView,
)

T = TypeVar("T")


@dataclass(slots=True)
class _ScopedFinanceData:
    organizations_by_id: dict[UUID, CanonicalOrganization]
    payments: list[CanonicalPayment]
    payment_allocations: list[CanonicalPaymentAllocation]
    financial_accounts: list[CanonicalFinancialAccount]
    financial_operations: list[CanonicalFinancialOperation]
    customer_returns: list[CanonicalCustomerReturn]
    customer_return_items: list[CanonicalCustomerReturnItem]
    purchases: list[CanonicalPurchase]
    supplier_returns: list[CanonicalSupplierReturn]
    writeoffs: list[CanonicalWriteoff]


class FinanceWorkspaceService:
    """Build finance workspace payloads from Canonical V2."""

    def __init__(self, store: CoreDataStore) -> None:
        self._store = store
        self._analytics = BusinessAnalyticsEngine(store)

    def list_workspace(
        self,
        analytics_query: AnalyticsQuery,
        workspace_query: FinanceWorkspaceQuery,
    ) -> FinanceWorkspaceResponse:
        summary_payload = self._analytics.build_summary(analytics_query)
        finance_report = self._analytics.build_finance(analytics_query)
        scoped = self._load_scoped_data(analytics_query)

        payment_rows = self._build_payment_rows(scoped)
        financial_operation_rows = self._build_financial_operation_rows(scoped)
        return_rows = self._build_return_rows(scoped)
        account_rows = self._build_account_rows(scoped)
        overview_rows = self._build_overview_rows(scoped, summary_payload.period)

        cash_operation_rows = [
            row for row in financial_operation_rows if row.source_type == "cash_operation"
        ]
        bank_operation_rows = [
            row for row in financial_operation_rows if row.source_type == "bank_operation"
        ]

        filters = self._build_filters_metadata(
            overview_rows,
            payment_rows,
            financial_operation_rows,
            return_rows,
            account_rows,
        )
        tabs = self._build_tabs(
            overview_rows,
            payment_rows,
            cash_operation_rows,
            bank_operation_rows,
            financial_operation_rows,
            return_rows,
            account_rows,
            finance_report.data_quality,
        )

        rows_map: dict[FinanceWorkspaceView, list[object]] = {
            FinanceWorkspaceView.OVERVIEW: self._sort_overview_rows(
                self._filter_overview_rows(overview_rows, workspace_query),
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            FinanceWorkspaceView.PAYMENTS: self._sort_payment_rows(
                self._filter_payment_rows(payment_rows, workspace_query),
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            FinanceWorkspaceView.CASH_OPERATIONS: self._sort_operation_rows(
                self._filter_operation_rows(cash_operation_rows, workspace_query),
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            FinanceWorkspaceView.BANK_OPERATIONS: self._sort_operation_rows(
                self._filter_operation_rows(bank_operation_rows, workspace_query),
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            FinanceWorkspaceView.FINANCIAL_OPERATIONS: self._sort_operation_rows(
                self._filter_operation_rows(financial_operation_rows, workspace_query),
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            FinanceWorkspaceView.RETURNS: self._sort_return_rows(
                self._filter_return_rows(return_rows, workspace_query),
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
            FinanceWorkspaceView.ACCOUNTS: self._sort_account_rows(
                self._filter_account_rows(account_rows, workspace_query),
                workspace_query.sort_by,
                workspace_query.sort_order,
            ),
        }
        active_rows = rows_map[workspace_query.view]
        pagination = self._paginate(active_rows, workspace_query.page, workspace_query.page_size)
        start = pagination.page_size * (pagination.page - 1)
        end = start + pagination.page_size
        page_rows = active_rows[start:end]

        return FinanceWorkspaceResponse(
            period=summary_payload.period,
            active_view=workspace_query.view,
            summary=self._build_summary(scoped, summary_payload, finance_report),
            coverage=self._build_coverage(finance_report),
            tabs=tabs,
            filters=filters,
            data_quality=finance_report.data_quality,
            rows=FinanceWorkspaceRows(
                overview=page_rows if workspace_query.view is FinanceWorkspaceView.OVERVIEW else [],
                payments=page_rows if workspace_query.view is FinanceWorkspaceView.PAYMENTS else [],
                cash_operations=(
                    page_rows
                    if workspace_query.view is FinanceWorkspaceView.CASH_OPERATIONS
                    else []
                ),
                bank_operations=(
                    page_rows
                    if workspace_query.view is FinanceWorkspaceView.BANK_OPERATIONS
                    else []
                ),
                financial_operations=(
                    page_rows
                    if workspace_query.view is FinanceWorkspaceView.FINANCIAL_OPERATIONS
                    else []
                ),
                returns=page_rows if workspace_query.view is FinanceWorkspaceView.RETURNS else [],
                accounts=page_rows if workspace_query.view is FinanceWorkspaceView.ACCOUNTS else [],
            ),
            pagination=pagination,
        )

    def _build_summary(
        self,
        scoped: _ScopedFinanceData,
        summary_payload: object,
        finance_report: object,
    ) -> FinanceWorkspaceSummary:
        business = summary_payload.business
        return FinanceWorkspaceSummary(
            payments_received=business.payments_received,
            verified_cash_in=business.verified_cash_in,
            verified_cash_out=business.verified_cash_out,
            net_cash_flow=business.cash_flow,
            customer_return_value=business.customer_return_value,
            financial_operations_count=AnalyticsMetricValue(
                value=(
                    Decimal(len(scoped.financial_operations))
                    if scoped.financial_operations
                    else None
                ),
                previous_value=None,
                delta=None,
                percent_delta=None,
                unit="count",
                status=_status_from_quality_rows(scoped.financial_operations),
                data_status=_status_from_quality_rows(scoped.financial_operations),
                coverage=1 if scoped.financial_operations else 0,
                confidence=None,
                currency=None,
                record_count=len(scoped.financial_operations),
                note="Количество canonical финансовых операций в выбранном контексте.",
            ),
        )

    def _build_coverage(self, finance_report: object) -> list[FinanceWorkspaceCoverageItem]:
        items: list[FinanceWorkspaceCoverageItem] = [
            FinanceWorkspaceCoverageItem(
                key="payments",
                label="Платежи клиентов",
                status=_to_capability(finance_report.payments_received.data_status),
                message=self._metric_message(
                    finance_report.payments_received,
                    fallback="Платежи клиентов пока не загружены.",
                ),
                affected_domains=["payments"],
            ),
            FinanceWorkspaceCoverageItem(
                key="cash_out",
                label="Денежные расходы",
                status=_to_capability(finance_report.expenses.data_status),
                message=(
                    "Нет подтверждённых данных о денежных расходах"
                    if finance_report.expenses.data_status == AnalyticsDataStatus.NO_VERIFIED_DATA
                    else self._metric_message(
                        finance_report.expenses,
                        fallback="Расходные денежные операции не найдены.",
                    )
                ),
                affected_domains=["cash_operations", "bank_operations", "financial_operations"],
            ),
            FinanceWorkspaceCoverageItem(
                key="bank_operations",
                label="Банковские операции",
                status=_to_capability(finance_report.bank_operations.data_status),
                message=self._metric_message(
                    finance_report.bank_operations,
                    fallback="Банковские операции в текущем срезе отсутствуют.",
                ),
                affected_domains=["bank_operations"],
            ),
            FinanceWorkspaceCoverageItem(
                key="returns",
                label="Стоимость возвратов",
                status=_to_capability(finance_report.by_category[0].data_status)
                if finance_report.by_category
                else FinanceWorkspaceCapabilityStatus.NO_DATA,
                message="Возвраты считаются отдельно от денежных возвратов клиентам.",
                affected_domains=["returns"],
            ),
        ]
        for item in finance_report.data_quality.items:
            if item.metric_key in {"payments_received", "expenses", "cash_flow"}:
                continue
            items.append(
                FinanceWorkspaceCoverageItem(
                    key=item.metric_key,
                    label=_coverage_label(item.metric_key),
                    status=_to_capability(item.data_status),
                    message=item.message or _coverage_fallback_message(item.metric_key),
                    affected_domains=_coverage_domains(item.metric_key),
                )
            )
        return items

    def _metric_message(self, metric: AnalyticsMetricValue, fallback: str) -> str:
        if metric.note:
            return metric.note
        if metric.data_status == AnalyticsDataStatus.NO_VERIFIED_DATA:
            return fallback
        if metric.data_status == AnalyticsDataStatus.NO_DATA:
            return fallback
        if metric.value is not None:
            return "Данные доступны в canonical финансовом слое."
        return fallback

    def _build_tabs(
        self,
        overview_rows: list[FinanceWorkspaceOverviewRow],
        payment_rows: list[FinanceWorkspacePaymentRow],
        cash_rows: list[FinanceWorkspaceOperationRow],
        bank_rows: list[FinanceWorkspaceOperationRow],
        operation_rows: list[FinanceWorkspaceOperationRow],
        return_rows: list[FinanceWorkspaceReturnRow],
        account_rows: list[FinanceWorkspaceAccountRow],
        data_quality: AnalyticsDataQualityReport,
    ) -> list[FinanceWorkspaceTabStatus]:
        return [
            FinanceWorkspaceTabStatus(
                view=FinanceWorkspaceView.OVERVIEW,
                label="Обзор",
                count=len(overview_rows),
                status=FinanceWorkspaceCapabilityStatus.AVAILABLE
                if overview_rows
                else FinanceWorkspaceCapabilityStatus.NO_DATA,
            ),
            FinanceWorkspaceTabStatus(
                view=FinanceWorkspaceView.PAYMENTS,
                label="Платежи",
                count=len(payment_rows),
                status=_to_capability(_status_from_quality_rows(payment_rows)),
            ),
            FinanceWorkspaceTabStatus(
                view=FinanceWorkspaceView.CASH_OPERATIONS,
                label="Кассовые операции",
                count=len(cash_rows),
                status=_to_capability(_status_from_quality_rows(cash_rows)),
                note="Кассовые операции и клиентские платежи показаны раздельно.",
            ),
            FinanceWorkspaceTabStatus(
                view=FinanceWorkspaceView.BANK_OPERATIONS,
                label="Банковские операции",
                count=len(bank_rows),
                status=_to_capability(_status_from_quality_rows(bank_rows)),
            ),
            FinanceWorkspaceTabStatus(
                view=FinanceWorkspaceView.FINANCIAL_OPERATIONS,
                label="Финансовые операции",
                count=len(operation_rows),
                status=_to_capability(_status_from_quality_rows(operation_rows)),
            ),
            FinanceWorkspaceTabStatus(
                view=FinanceWorkspaceView.RETURNS,
                label="Возвраты",
                count=len(return_rows),
                status=_to_capability(_status_from_quality_rows(return_rows)),
                note="Стоимость возвратов, не денежные возвраты.",
            ),
            FinanceWorkspaceTabStatus(
                view=FinanceWorkspaceView.ACCOUNTS,
                label="Счета",
                count=len(account_rows),
                status=_to_capability(_status_from_quality_rows(account_rows)),
            ),
        ]

    def _build_filters_metadata(
        self,
        overview_rows: list[FinanceWorkspaceOverviewRow],
        payment_rows: list[FinanceWorkspacePaymentRow],
        operation_rows: list[FinanceWorkspaceOperationRow],
        return_rows: list[FinanceWorkspaceReturnRow],
        account_rows: list[FinanceWorkspaceAccountRow],
    ) -> FinanceWorkspaceFiltersMetadata:
        org_counter = Counter(row.organization_name for row in overview_rows)
        direction_counter = Counter(row.direction for row in operation_rows)
        op_type_counter = Counter((row.operation_type or "Без типа") for row in operation_rows)
        payment_type_counter = Counter((row.payment_type or "Не указан") for row in payment_rows)
        counterparty_counter = Counter(
            name
            for name in [
                *(row.customer_name for row in payment_rows),
                *(row.counterparty_name for row in operation_rows),
                *(row.customer_name for row in return_rows),
            ]
            if name
        )
        account_counter = Counter(
            label
            for label in [
                *(row.cashbox_or_account for row in payment_rows),
                *(row.account_label for row in operation_rows),
                *((row.account_name or row.account_code) for row in account_rows),
            ]
            if label
        )
        currency_counter = Counter(
            code
            for code in [
                *(row.currency_code for row in payment_rows),
                *(row.currency_code for row in operation_rows),
                *(row.currency_code for row in return_rows),
                *(row.currency_code for row in account_rows),
            ]
            if code
        )
        quality_counter = Counter(
            str(status)
            for status in [
                *(row.data_quality_status for row in payment_rows),
                *(row.data_quality_status for row in operation_rows),
                *(row.data_quality_status for row in return_rows),
                *(row.data_quality_status for row in account_rows),
            ]
        )
        return FinanceWorkspaceFiltersMetadata(
            organizations=_options_from_counter(org_counter),
            directions=_options_from_counter(direction_counter, label_map=_direction_label_map()),
            operation_types=_options_from_counter(op_type_counter),
            payment_types=_options_from_counter(payment_type_counter),
            counterparties=_options_from_counter(counterparty_counter),
            accounts=_options_from_counter(account_counter),
            currencies=_options_from_counter(currency_counter),
            data_quality=_options_from_counter(quality_counter, label_map=_quality_label_map()),
        )

    def _build_overview_rows(
        self,
        scoped: _ScopedFinanceData,
        period: object,
    ) -> list[FinanceWorkspaceOverviewRow]:
        rows: list[FinanceWorkspaceOverviewRow] = []
        payments_by_org: dict[UUID, list[CanonicalPayment]] = defaultdict(list)
        operations_by_org: dict[UUID, list[CanonicalFinancialOperation]] = defaultdict(list)
        returns_by_org: dict[UUID, list[CanonicalCustomerReturn]] = defaultdict(list)
        purchases_by_org: dict[UUID, list[CanonicalPurchase]] = defaultdict(list)
        writeoffs_by_org: dict[UUID, list[CanonicalWriteoff]] = defaultdict(list)
        for row in scoped.payments:
            payments_by_org[row.organization_id].append(row)
        for row in scoped.financial_operations:
            operations_by_org[row.organization_id].append(row)
        for row in scoped.customer_returns:
            returns_by_org[row.organization_id].append(row)
        for row in scoped.purchases:
            purchases_by_org[row.organization_id].append(row)
        for row in scoped.writeoffs:
            writeoffs_by_org[row.organization_id].append(row)

        for organization in scoped.organizations_by_id.values():
            payments = payments_by_org.get(organization.organization_id, [])
            operations = operations_by_org.get(organization.organization_id, [])
            returns = returns_by_org.get(organization.organization_id, [])
            rows.append(
                FinanceWorkspaceOverviewRow(
                    organization_id=organization.organization_id,
                    organization_name=organization.name,
                    payments_received=_sum_amount(payments, "amount"),
                    verified_cash_in=_sum_amount(
                        [row for row in operations if _is_verified_inflow(row)],
                        "amount",
                    ),
                    verified_cash_out=_sum_amount(
                        [row for row in operations if _is_verified_outflow(row)],
                        "amount",
                    ),
                    customer_return_value=_sum_amount(returns, "total_amount"),
                    financial_operations_count=len(operations),
                    payments_count=len(payments),
                    returns_count=len(returns),
                    purchases_count=len(purchases_by_org.get(organization.organization_id, [])),
                    writeoffs_count=len(writeoffs_by_org.get(organization.organization_id, [])),
                    data_status=_merge_statuses(
                        [
                            _status_from_quality_rows(payments),
                            _status_from_quality_rows(operations),
                            _status_from_quality_rows(returns),
                        ]
                    ),
                )
            )
        return rows

    def _build_payment_rows(self, scoped: _ScopedFinanceData) -> list[FinanceWorkspacePaymentRow]:
        allocations_by_payment: dict[UUID, list[CanonicalPaymentAllocation]] = defaultdict(list)
        for allocation in scoped.payment_allocations:
            allocations_by_payment[allocation.payment_id].append(allocation)

        rows: list[FinanceWorkspacePaymentRow] = []
        for payment in scoped.payments:
            organization = scoped.organizations_by_id[payment.organization_id]
            allocations = allocations_by_payment.get(payment.id, [])
            linked = next((item for item in allocations if item.order_id or item.sale_id), None)
            account_label = payment.cashbox_code or payment.bank_account_code
            rows.append(
                FinanceWorkspacePaymentRow(
                    payment_id=payment.id,
                    source_external_id=payment.source_external_id,
                    payment_number=payment.cashin_number or payment.payment_id or payment.cashin_id,
                    paid_at=payment.paid_at or payment.cashin_date,
                    organization_id=organization.organization_id,
                    organization_name=organization.name,
                    customer_id=payment.customer_id,
                    customer_name=payment.customer_name,
                    amount=payment.amount,
                    currency_code=payment.currency_code,
                    payment_type=(
                        payment.normalized_payment_type or payment.source_payment_type_code
                    ),
                    cashbox_or_account=account_label,
                    purpose=payment.purpose,
                    allocation_status=(
                        "Связан с конкретным заказом"
                        if linked is not None
                        else "Не привязан к конкретному заказу"
                    ),
                    linked_order_id=linked.order_id if linked is not None else None,
                    linked_order_external_id=(
                        linked.order_external_id if linked is not None else None
                    ),
                    linked_sale_id=linked.sale_id if linked is not None else None,
                    linked_sale_external_id=linked.sale_external_id if linked is not None else None,
                    linked_order_number=linked.order_external_id if linked is not None else None,
                    data_quality_status=payment.data_quality_status,
                    data_status=_status_from_quality_rows([payment]),
                    provenance=_build_provenance(payment),
                )
            )
        return rows

    def _build_financial_operation_rows(
        self,
        scoped: _ScopedFinanceData,
    ) -> list[FinanceWorkspaceOperationRow]:
        accounts_by_id = {account.id: account for account in scoped.financial_accounts}
        rows: list[FinanceWorkspaceOperationRow] = []
        for operation in scoped.financial_operations:
            organization = scoped.organizations_by_id[operation.organization_id]
            account = accounts_by_id.get(operation.account_id) if operation.account_id else None
            account_label = _account_label(account, operation.account_code)
            source_type = _source_type_from_operation(operation)
            overlap_note = None
            overlaps_customer_payment = False
            if (
                source_type == "cash_operation"
                and operation.source_document_type == "customer_payment"
            ):
                overlaps_customer_payment = True
                overlap_note = "Связано с клиентским платежом"
            elif operation.source_endpoint == "cashin$export":
                overlaps_customer_payment = True
                overlap_note = "Источник SmartUp: клиентский платёж"
            rows.append(
                FinanceWorkspaceOperationRow(
                    operation_id=operation.id,
                    source_external_id=operation.source_external_id,
                    source_type=source_type,
                    source_label=_source_label(source_type),
                    operation_number=operation.operation_number,
                    operation_at=operation.operation_at or operation.operation_date,
                    organization_id=organization.organization_id,
                    organization_name=organization.name,
                    operation_type=(
                        operation.normalized_operation_type or operation.source_operation_type
                    ),
                    direction=_direction_from_canonical(operation.direction),
                    account_id=operation.account_id,
                    account_label=account_label,
                    counterparty_type=operation.counterparty_type,
                    counterparty_id=operation.counterparty_customer_id,
                    counterparty_name=operation.counterparty_name,
                    purpose=operation.purpose or operation.note,
                    amount=operation.amount,
                    currency_code=operation.currency_code,
                    posted=operation.posted,
                    is_internal_transfer=operation.is_internal_transfer,
                    overlaps_customer_payment=overlaps_customer_payment,
                    overlap_note=overlap_note,
                    source_document_type=operation.source_document_type,
                    source_document_external_id=operation.source_document_external_id,
                    data_quality_status=operation.data_quality_status,
                    data_status=_status_from_quality_rows([operation]),
                    provenance=_build_provenance(operation),
                )
            )
        return rows

    def _build_return_rows(self, scoped: _ScopedFinanceData) -> list[FinanceWorkspaceReturnRow]:
        items_by_return: dict[UUID, list[CanonicalCustomerReturnItem]] = defaultdict(list)
        for item in scoped.customer_return_items:
            items_by_return[item.customer_return_id].append(item)
        rows: list[FinanceWorkspaceReturnRow] = []
        for customer_return in scoped.customer_returns:
            organization = scoped.organizations_by_id[customer_return.organization_id]
            items = items_by_return.get(customer_return.id, [])
            rows.append(
                FinanceWorkspaceReturnRow(
                    customer_return_id=customer_return.id,
                    source_external_id=customer_return.source_external_id,
                    return_number=customer_return.return_number or customer_return.return_id,
                    return_at=customer_return.return_at or customer_return.delivery_date,
                    organization_id=organization.organization_id,
                    organization_name=organization.name,
                    customer_id=customer_return.customer_id,
                    customer_name=customer_return.customer_name,
                    value=customer_return.total_amount,
                    currency_code=customer_return.currency_code,
                    returned_units=customer_return.returned_quantity,
                    products_count=len(items),
                    reason_code=customer_return.return_reason_code,
                    status=customer_return.display_status,
                    cash_refund_status="Денежный возврат не подтверждён",
                    data_quality_status=customer_return.data_quality_status,
                    data_status=_status_from_quality_rows([customer_return]),
                    provenance=_build_provenance(customer_return),
                )
            )
        return rows

    def _build_account_rows(self, scoped: _ScopedFinanceData) -> list[FinanceWorkspaceAccountRow]:
        rows: list[FinanceWorkspaceAccountRow] = []
        for account in scoped.financial_accounts:
            organization = scoped.organizations_by_id[account.organization_id]
            rows.append(
                FinanceWorkspaceAccountRow(
                    account_id=account.id,
                    source_external_id=account.source_external_id,
                    organization_id=organization.organization_id,
                    organization_name=organization.name,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    account_type=account.account_type,
                    currency_code=account.currency_code,
                    bank_name=account.bank_name,
                    bank_account_code=account.bank_account_code,
                    cashbox_code=account.cashbox_code,
                    data_quality_status=account.data_quality_status,
                    data_status=_status_from_quality_rows([account]),
                    provenance=_build_provenance(account),
                )
            )
        return rows

    def _load_scoped_data(self, analytics_query: AnalyticsQuery) -> _ScopedFinanceData:
        organization_ids = set(analytics_query.organization_ids)
        organizations = {
            item.organization_id: item
            for item in self._store.list_canonical_organizations()
            if not organization_ids or item.organization_id in organization_ids
        }

        def scoped_rows(
            loader: Callable[[UUID | None], list[T] | object],
        ) -> list[T]:
            rows = list(loader(None))
            if not organization_ids:
                return rows
            return [
                row
                for row in rows
                if hasattr(row, "organization_id") and row.organization_id in organization_ids
            ]

        payments = _filter_by_window(
            scoped_rows(self._store.list_canonical_payments),
            analytics_query,
            lambda row: row.paid_at or row.cashin_date,
        )
        allocations = scoped_rows(self._store.list_canonical_payment_allocations)
        operations = _filter_by_window(
            scoped_rows(self._store.list_canonical_financial_operations),
            analytics_query,
            lambda row: row.operation_at or row.operation_date,
        )
        returns = _filter_by_window(
            scoped_rows(self._store.list_canonical_customer_returns),
            analytics_query,
            lambda row: row.return_at or row.delivery_date,
        )
        purchases = _filter_by_window(
            scoped_rows(self._store.list_canonical_purchases),
            analytics_query,
            lambda row: row.document_at,
        )
        supplier_returns = _filter_by_window(
            scoped_rows(self._store.list_canonical_supplier_returns),
            analytics_query,
            lambda row: row.document_at,
        )
        writeoffs = _filter_by_window(
            scoped_rows(self._store.list_canonical_writeoffs),
            analytics_query,
            lambda row: row.document_at or row.writeoff_date,
        )
        return _ScopedFinanceData(
            organizations_by_id=organizations,
            payments=payments,
            payment_allocations=allocations,
            financial_accounts=scoped_rows(self._store.list_canonical_financial_accounts),
            financial_operations=operations,
            customer_returns=returns,
            customer_return_items=scoped_rows(self._store.list_canonical_customer_return_items),
            purchases=purchases,
            supplier_returns=supplier_returns,
            writeoffs=writeoffs,
        )

    def _filter_overview_rows(
        self,
        rows: list[FinanceWorkspaceOverviewRow],
        query: FinanceWorkspaceQuery,
    ) -> list[FinanceWorkspaceOverviewRow]:
        search = _normalized_search(query.search)
        if not search:
            return rows
        return [row for row in rows if search in row.organization_name.lower()]

    def _filter_payment_rows(
        self,
        rows: list[FinanceWorkspacePaymentRow],
        query: FinanceWorkspaceQuery,
    ) -> list[FinanceWorkspacePaymentRow]:
        search = _normalized_search(query.search)
        result: list[FinanceWorkspacePaymentRow] = []
        for row in rows:
            if query.payment_type and (row.payment_type or "") not in query.payment_type:
                continue
            if query.counterparty and (row.customer_name or "") not in query.counterparty:
                continue
            if query.account and (row.cashbox_or_account or "") not in query.account:
                continue
            if query.currency and (row.currency_code or "") not in query.currency:
                continue
            if query.data_quality and row.data_quality_status not in query.data_quality:
                continue
            if not _amount_in_range(row.amount, query.amount_min, query.amount_max):
                continue
            if search and not _matches_search(
                search,
                [
                    row.source_external_id,
                    row.payment_number,
                    row.organization_name,
                    row.customer_name,
                    row.purpose,
                    row.cashbox_or_account,
                ],
            ):
                continue
            result.append(row)
        return result

    def _filter_operation_rows(
        self,
        rows: list[FinanceWorkspaceOperationRow],
        query: FinanceWorkspaceQuery,
    ) -> list[FinanceWorkspaceOperationRow]:
        search = _normalized_search(query.search)
        result: list[FinanceWorkspaceOperationRow] = []
        for row in rows:
            if query.direction and row.direction not in query.direction:
                continue
            if query.operation_type and (row.operation_type or "") not in query.operation_type:
                continue
            if query.counterparty and (row.counterparty_name or "") not in query.counterparty:
                continue
            if query.account and (row.account_label or "") not in query.account:
                continue
            if query.currency and (row.currency_code or "") not in query.currency:
                continue
            if query.data_quality and row.data_quality_status not in query.data_quality:
                continue
            if not _amount_in_range(row.amount, query.amount_min, query.amount_max):
                continue
            if search and not _matches_search(
                search,
                [
                    row.source_external_id,
                    row.operation_number,
                    row.organization_name,
                    row.counterparty_name,
                    row.account_label,
                    row.purpose,
                    row.source_document_external_id,
                ],
            ):
                continue
            result.append(row)
        return result

    def _filter_return_rows(
        self,
        rows: list[FinanceWorkspaceReturnRow],
        query: FinanceWorkspaceQuery,
    ) -> list[FinanceWorkspaceReturnRow]:
        search = _normalized_search(query.search)
        result: list[FinanceWorkspaceReturnRow] = []
        for row in rows:
            if query.counterparty and (row.customer_name or "") not in query.counterparty:
                continue
            if query.currency and (row.currency_code or "") not in query.currency:
                continue
            if query.data_quality and row.data_quality_status not in query.data_quality:
                continue
            if not _amount_in_range(row.value, query.amount_min, query.amount_max):
                continue
            if search and not _matches_search(
                search,
                [
                    row.source_external_id,
                    row.return_number,
                    row.organization_name,
                    row.customer_name,
                    row.reason_code,
                ],
            ):
                continue
            result.append(row)
        return result

    def _filter_account_rows(
        self,
        rows: list[FinanceWorkspaceAccountRow],
        query: FinanceWorkspaceQuery,
    ) -> list[FinanceWorkspaceAccountRow]:
        search = _normalized_search(query.search)
        result: list[FinanceWorkspaceAccountRow] = []
        for row in rows:
            if (
                query.account
                and row.account_code not in query.account
                and (row.account_name or "") not in query.account
            ):
                continue
            if query.currency and (row.currency_code or "") not in query.currency:
                continue
            if query.data_quality and row.data_quality_status not in query.data_quality:
                continue
            if search and not _matches_search(
                search,
                [
                    row.account_code,
                    row.account_name,
                    row.bank_account_code,
                    row.cashbox_code,
                    row.organization_name,
                ],
            ):
                continue
            result.append(row)
        return result

    def _sort_overview_rows(
        self,
        rows: list[FinanceWorkspaceOverviewRow],
        sort_by: FinanceWorkspaceSortBy,
        sort_order: FinanceWorkspaceSortOrder,
    ) -> list[FinanceWorkspaceOverviewRow]:
        reverse = sort_order is FinanceWorkspaceSortOrder.DESC
        if sort_by is FinanceWorkspaceSortBy.AMOUNT:
            return sorted(
                rows,
                key=lambda row: row.payments_received or Decimal("0"),
                reverse=reverse,
            )
        return sorted(rows, key=lambda row: row.organization_name.lower(), reverse=reverse)

    def _sort_payment_rows(
        self,
        rows: list[FinanceWorkspacePaymentRow],
        sort_by: FinanceWorkspaceSortBy,
        sort_order: FinanceWorkspaceSortOrder,
    ) -> list[FinanceWorkspacePaymentRow]:
        reverse = sort_order is FinanceWorkspaceSortOrder.DESC
        key_map: dict[FinanceWorkspaceSortBy, Callable[[FinanceWorkspacePaymentRow], object]] = {
            FinanceWorkspaceSortBy.DATE: (
                lambda row: row.paid_at or datetime.min.replace(tzinfo=UTC)
            ),
            FinanceWorkspaceSortBy.AMOUNT: lambda row: row.amount or Decimal("0"),
            FinanceWorkspaceSortBy.ORGANIZATION: lambda row: row.organization_name.lower(),
            FinanceWorkspaceSortBy.CUSTOMER: lambda row: (row.customer_name or "").lower(),
            FinanceWorkspaceSortBy.ACCOUNT: lambda row: (row.cashbox_or_account or "").lower(),
            FinanceWorkspaceSortBy.OPERATION_TYPE: lambda row: (row.payment_type or "").lower(),
            FinanceWorkspaceSortBy.DIRECTION: lambda row: "inflow",
        }
        return sorted(
            rows,
            key=key_map.get(sort_by, key_map[FinanceWorkspaceSortBy.DATE]),
            reverse=reverse,
        )

    def _sort_operation_rows(
        self,
        rows: list[FinanceWorkspaceOperationRow],
        sort_by: FinanceWorkspaceSortBy,
        sort_order: FinanceWorkspaceSortOrder,
    ) -> list[FinanceWorkspaceOperationRow]:
        reverse = sort_order is FinanceWorkspaceSortOrder.DESC
        key_map: dict[FinanceWorkspaceSortBy, Callable[[FinanceWorkspaceOperationRow], object]] = {
            FinanceWorkspaceSortBy.DATE: (
                lambda row: row.operation_at or datetime.min.replace(tzinfo=UTC)
            ),
            FinanceWorkspaceSortBy.AMOUNT: lambda row: row.amount or Decimal("0"),
            FinanceWorkspaceSortBy.ORGANIZATION: lambda row: row.organization_name.lower(),
            FinanceWorkspaceSortBy.OPERATION_TYPE: lambda row: (row.operation_type or "").lower(),
            FinanceWorkspaceSortBy.DIRECTION: lambda row: row.direction.value,
            FinanceWorkspaceSortBy.CUSTOMER: lambda row: (row.counterparty_name or "").lower(),
            FinanceWorkspaceSortBy.ACCOUNT: lambda row: (row.account_label or "").lower(),
        }
        return sorted(
            rows,
            key=key_map.get(sort_by, key_map[FinanceWorkspaceSortBy.DATE]),
            reverse=reverse,
        )

    def _sort_return_rows(
        self,
        rows: list[FinanceWorkspaceReturnRow],
        sort_by: FinanceWorkspaceSortBy,
        sort_order: FinanceWorkspaceSortOrder,
    ) -> list[FinanceWorkspaceReturnRow]:
        reverse = sort_order is FinanceWorkspaceSortOrder.DESC
        key_map: dict[FinanceWorkspaceSortBy, Callable[[FinanceWorkspaceReturnRow], object]] = {
            FinanceWorkspaceSortBy.DATE: (
                lambda row: row.return_at or datetime.min.replace(tzinfo=UTC)
            ),
            FinanceWorkspaceSortBy.AMOUNT: lambda row: row.value or Decimal("0"),
            FinanceWorkspaceSortBy.ORGANIZATION: lambda row: row.organization_name.lower(),
            FinanceWorkspaceSortBy.CUSTOMER: lambda row: (row.customer_name or "").lower(),
            FinanceWorkspaceSortBy.OPERATION_TYPE: lambda row: (row.reason_code or "").lower(),
            FinanceWorkspaceSortBy.DIRECTION: lambda row: "return",
            FinanceWorkspaceSortBy.ACCOUNT: lambda row: "",
        }
        return sorted(
            rows,
            key=key_map.get(sort_by, key_map[FinanceWorkspaceSortBy.DATE]),
            reverse=reverse,
        )

    def _sort_account_rows(
        self,
        rows: list[FinanceWorkspaceAccountRow],
        sort_by: FinanceWorkspaceSortBy,
        sort_order: FinanceWorkspaceSortOrder,
    ) -> list[FinanceWorkspaceAccountRow]:
        reverse = sort_order is FinanceWorkspaceSortOrder.DESC
        if sort_by is FinanceWorkspaceSortBy.ORGANIZATION:
            return sorted(rows, key=lambda row: row.organization_name.lower(), reverse=reverse)
        return sorted(
            rows,
            key=lambda row: (row.account_name or row.account_code).lower(),
            reverse=reverse,
        )

    def _paginate(
        self,
        rows: list[object],
        page: int,
        page_size: int,
    ) -> FinanceWorkspacePagination:
        total_items = len(rows)
        total_pages = max(1, ceil(total_items / page_size)) if page_size > 0 else 1
        safe_page = min(max(page, 1), total_pages)
        return FinanceWorkspacePagination(
            page=safe_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )


def _filter_by_window[T](
    rows: list[T],
    analytics_query: AnalyticsQuery,
    get_date: Callable[[T], datetime | None],
) -> list[T]:
    window = _build_period_window(analytics_query)
    if window.current_start is None and window.current_end is None:
        return rows
    filtered: list[T] = []
    for row in rows:
        value = get_date(row)
        if value is None:
            continue
        if window.current_start and value < window.current_start:
            continue
        if window.current_end and value > window.current_end:
            continue
        filtered.append(row)
    return filtered


def _build_provenance(
    row: CanonicalPayment
    | CanonicalFinancialOperation
    | CanonicalCustomerReturn
    | CanonicalFinancialAccount,
) -> FinanceWorkspaceProvenance:
    return FinanceWorkspaceProvenance(
        source_endpoint=row.source_endpoint,
        source_external_id=row.source_external_id,
        source_raw_record_id=row.source_raw_record_id,
        request_filial_id=row.request_filial_id,
        response_filial_id=row.response_filial_id,
        request_company_id=row.request_company_id,
        request_project_code=row.request_project_code,
        data_quality_status=row.data_quality_status,
    )


def _status_from_quality_rows(
    rows: list[object],
    *,
    none_status: AnalyticsDataStatus = AnalyticsDataStatus.NO_DATA,
) -> AnalyticsDataStatus:
    if not rows:
        return none_status
    qualities = {getattr(row, "data_quality_status", None) for row in rows}
    if CanonicalDataQualityStatus.UNSAFE in qualities:
        return AnalyticsDataStatus.UNRESOLVED
    if CanonicalDataQualityStatus.UNRESOLVED in qualities:
        return AnalyticsDataStatus.UNRESOLVED
    if CanonicalDataQualityStatus.PARTIAL in qualities:
        return AnalyticsDataStatus.PARTIAL
    if CanonicalDataQualityStatus.VERIFIED in qualities:
        return AnalyticsDataStatus.AVAILABLE
    return none_status


def _merge_statuses(statuses: list[AnalyticsDataStatus]) -> AnalyticsDataStatus:
    filtered = [
        status
        for status in statuses
        if status not in {AnalyticsDataStatus.NO_DATA, AnalyticsDataStatus.NOT_AVAILABLE}
    ]
    if not filtered:
        return AnalyticsDataStatus.NO_DATA
    if AnalyticsDataStatus.UNRESOLVED in filtered:
        return AnalyticsDataStatus.UNRESOLVED
    if AnalyticsDataStatus.PARTIAL in filtered:
        return AnalyticsDataStatus.PARTIAL
    if AnalyticsDataStatus.NO_VERIFIED_DATA in filtered and len(filtered) == 1:
        return AnalyticsDataStatus.NO_VERIFIED_DATA
    return AnalyticsDataStatus.AVAILABLE


def _sum_amount(rows: list[object], field_name: str) -> Decimal | None:
    if not rows:
        return None
    values = [getattr(row, field_name) for row in rows if getattr(row, field_name) is not None]
    if not values:
        return None
    return sum(values, Decimal("0"))


def _coverage_label(metric_key: str) -> str:
    labels = {
        "sales": "Выручка",
        "orders": "Заказы",
        "realised_sales": "Реализованные продажи",
        "sold_units": "Проданные единицы",
        "average_order": "Средний чек",
        "unique_customers": "Клиенты",
        "unique_products": "Товары",
        "current_stock": "Текущие остатки",
        "visits": "Визиты",
        "verified_cash_in": "Подтверждённые поступления",
        "verified_cash_out": "Подтверждённые расходы",
        "returns": "Возвраты",
        "customers": "Клиентский слой",
    }
    return labels.get(metric_key, metric_key.replace("_", " ").capitalize())


def _coverage_domains(metric_key: str) -> list[str]:
    mapping = {
        "sales": ["payments", "financial_operations"],
        "orders": ["payments"],
        "realised_sales": ["payments"],
        "sold_units": ["payments"],
        "average_order": ["payments"],
        "unique_customers": ["payments", "returns"],
        "unique_products": ["returns"],
        "current_stock": ["accounts"],
        "visits": ["financial_operations"],
        "verified_cash_in": ["cash_operations", "bank_operations", "financial_operations"],
        "verified_cash_out": ["cash_operations", "bank_operations", "financial_operations"],
        "returns": ["returns"],
        "customers": ["payments", "returns"],
    }
    return mapping.get(metric_key, ["financial_operations"])


def _coverage_fallback_message(metric_key: str) -> str:
    mapping = {
        "sales": "Выручка пока недоступна в finance workspace.",
        "orders": "Заказы пока недоступны в finance workspace.",
        "realised_sales": "Подтверждённые продажи пока недоступны.",
        "sold_units": "Нет подтверждённых данных по проданным единицам.",
        "average_order": "Средний чек пока не рассчитан.",
        "unique_customers": "Клиентское покрытие пока ограничено.",
        "unique_products": "Покрытие по товарам пока ограничено.",
        "current_stock": "Остатки не входят в основной финансовый поток.",
        "visits": "Визиты не являются частью финансового слоя.",
        "verified_cash_in": "Подтверждённые поступления отсутствуют.",
        "verified_cash_out": "Подтверждённые денежные расходы отсутствуют.",
        "returns": "Возвраты пока не загружены.",
        "customers": "Клиентский слой финансов пока ограничен.",
    }
    return mapping.get(metric_key, "Данные для этого домена пока ограничены.")


def _is_verified_inflow(row: CanonicalFinancialOperation) -> bool:
    return (
        row.data_quality_status == CanonicalDataQualityStatus.VERIFIED
        and row.direction == CanonicalFinancialDirection.INFLOW
        and not row.is_internal_transfer
    )


def _is_verified_outflow(row: CanonicalFinancialOperation) -> bool:
    return (
        row.data_quality_status == CanonicalDataQualityStatus.VERIFIED
        and row.direction == CanonicalFinancialDirection.OUTFLOW
        and not row.is_internal_transfer
    )


def _direction_from_canonical(
    direction: CanonicalFinancialDirection | None,
) -> FinanceWorkspaceDirection:
    if direction == CanonicalFinancialDirection.INFLOW:
        return FinanceWorkspaceDirection.INFLOW
    if direction == CanonicalFinancialDirection.OUTFLOW:
        return FinanceWorkspaceDirection.OUTFLOW
    if direction == CanonicalFinancialDirection.TRANSFER:
        return FinanceWorkspaceDirection.TRANSFER
    return FinanceWorkspaceDirection.UNKNOWN


def _source_type_from_operation(operation: CanonicalFinancialOperation) -> str:
    endpoint = operation.source_endpoint.lower()
    if "bank_operation" in endpoint:
        return "bank_operation"
    if "cash_operation" in endpoint or "cashin" in endpoint:
        return "cash_operation"
    return "financial_operation"


def _source_label(source_type: str) -> str:
    if source_type == "bank_operation":
        return "Банковская операция"
    if source_type == "cash_operation":
        return "Кассовая операция"
    return "Финансовая операция"


def _account_label(
    account: CanonicalFinancialAccount | None,
    account_code: str | None,
) -> str | None:
    if account is None:
        return account_code
    parts = [account.account_name or account.account_code]
    if account.bank_account_code:
        parts.append(account.bank_account_code)
    elif account.cashbox_code:
        parts.append(account.cashbox_code)
    return " · ".join(part for part in parts if part)


def _normalized_search(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    return text or None


def _matches_search(search: str, values: list[str | None]) -> bool:
    haystack = " ".join(value for value in values if value).lower()
    return search in haystack


def _amount_in_range(
    amount: Decimal | None,
    minimum: Decimal | None,
    maximum: Decimal | None,
) -> bool:
    numeric = amount or Decimal("0")
    if minimum is not None and numeric < minimum:
        return False
    if maximum is not None and numeric > maximum:
        return False
    return True


def _to_capability(status: AnalyticsDataStatus) -> FinanceWorkspaceCapabilityStatus:
    if status == AnalyticsDataStatus.AVAILABLE:
        return FinanceWorkspaceCapabilityStatus.AVAILABLE
    if status == AnalyticsDataStatus.PARTIAL:
        return FinanceWorkspaceCapabilityStatus.PARTIAL
    if status == AnalyticsDataStatus.NO_VERIFIED_DATA:
        return FinanceWorkspaceCapabilityStatus.NO_VERIFIED_DATA
    if status == AnalyticsDataStatus.UNRESOLVED:
        return FinanceWorkspaceCapabilityStatus.UNRESOLVED
    if status == AnalyticsDataStatus.NOT_AVAILABLE:
        return FinanceWorkspaceCapabilityStatus.NOT_AVAILABLE
    return FinanceWorkspaceCapabilityStatus.NO_DATA


def _options_from_counter(
    counter: Counter[object],
    *,
    label_map: dict[object, str] | None = None,
) -> list[FinanceWorkspaceFilterOption]:
    options: list[FinanceWorkspaceFilterOption] = []
    for value, count in sorted(counter.items(), key=lambda item: str(item[0])):
        label = label_map.get(value, str(value)) if label_map else str(value)
        options.append(FinanceWorkspaceFilterOption(value=str(value), label=label, count=count))
    return options


def _direction_label_map() -> dict[object, str]:
    return {
        FinanceWorkspaceDirection.INFLOW: "Поступление",
        FinanceWorkspaceDirection.OUTFLOW: "Списание",
        FinanceWorkspaceDirection.TRANSFER: "Перевод",
        FinanceWorkspaceDirection.UNKNOWN: "Не определено",
    }


def _quality_label_map() -> dict[object, str]:
    return {
        "verified": "Подтверждено",
        "partial": "Частично",
        "unresolved": "Неразрешено",
        "unsafe": "Небезопасно",
    }
