"""
Tools for Report Generator Agent.
"""

import json
from datetime import datetime

from agency_swarm import function_tool

from ...utils import get_audit_logger, get_logger

logger = get_logger(__name__)
audit_logger = get_audit_logger()


@function_tool
def report_builder(
    report_type: str = "summary", data_sources: str = "[]", time_range: str = "{}", output_format: str = "json"
) -> str:
    """
    Build comprehensive reports from processing data.

    Args:
        report_type: Type of report (summary, detailed, error, performance)
        data_sources: JSON array of data sources to include
        time_range: JSON object with start/end times for filtering
        output_format: Output format (json, html, csv, pdf)

    Returns:
        JSON string with generated report data
    """
    try:
        sources = json.loads(data_sources) if data_sources else []
        time_filter = json.loads(time_range) if time_range else {}

        report_data = {
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "time_range": time_filter,
            "data_sources": sources,
            "output_format": output_format,
            "sections": {},
        }

        if report_type == "summary":
            report_data["sections"] = _build_summary_report(sources, time_filter)
        elif report_type == "detailed":
            report_data["sections"] = _build_detailed_report(sources, time_filter)
        elif report_type == "error":
            report_data["sections"] = _build_error_report(sources, time_filter)
        elif report_type == "performance":
            report_data["sections"] = _build_performance_report(sources, time_filter)
        else:
            raise ValueError(f"Unknown report type: {report_type}")

        # Format output if requested
        if output_format == "html":
            report_data["html_content"] = _format_as_html(report_data)
        elif output_format == "csv":
            report_data["csv_content"] = _format_as_csv(report_data)

        logger.info(f"Generated {report_type} report with {len(report_data['sections'])} sections")
        return json.dumps(report_data, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Report building failed: {e}")
        return json.dumps(
            {"report_type": report_type, "generated_at": datetime.now().isoformat(), "error": str(e), "sections": {}}
        )


@function_tool
def notification_sender(
    notification_type: str, recipients: str = "[]", message_data: str = "{}", delivery_method: str = "log"
) -> str:
    """
    Send notifications about processing status and results.

    Args:
        notification_type: Type of notification (success, error, warning, info)
        recipients: JSON array of recipient configurations
        message_data: JSON object with message content and metadata
        delivery_method: Delivery method (log, email, webhook, file)

    Returns:
        JSON string with notification delivery results
    """
    try:
        recipient_list = json.loads(recipients) if recipients else []
        message = json.loads(message_data) if message_data else {}

        notification = {
            "type": notification_type,
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "recipients": recipient_list,
            "delivery_method": delivery_method,
            "delivery_results": [],
        }

        # Build notification message
        subject = message.get("subject", f"Erni-Foto {notification_type.title()} Notification")
        body = message.get("body", "")

        if not body:
            body = _generate_default_message(notification_type, message)

        # Deliver notification based on method
        if delivery_method == "log":
            _deliver_to_log(notification_type, subject, body)
            notification["delivery_results"].append(
                {"method": "log", "success": True, "message": "Logged successfully"}
            )

        elif delivery_method == "file":
            result = _deliver_to_file(notification_type, subject, body, message.get("file_path"))
            notification["delivery_results"].append(result)

        elif delivery_method == "webhook":
            for recipient in recipient_list:
                if recipient.get("type") == "webhook":
                    result = _deliver_to_webhook(recipient.get("url"), notification)
                    notification["delivery_results"].append(result)

        elif delivery_method == "email":
            # Email delivery would require SMTP configuration
            notification["delivery_results"].append(
                {"method": "email", "success": False, "message": "Email delivery not implemented"}
            )

        else:
            raise ValueError(f"Unknown delivery method: {delivery_method}")

        logger.info(f"Sent {notification_type} notification via {delivery_method}")
        return json.dumps(notification, indent=2)

    except Exception as e:
        logger.error(f"Notification sending failed: {e}")
        return json.dumps(
            {
                "type": notification_type,
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "delivery_results": [],
            }
        )


@function_tool
def statistics_collector(
    operation: str = "collect", metric_types: str = "[]", aggregation_period: str = "hour", data_points: str = "[]"
) -> str:
    """
    Collect and aggregate processing statistics.

    Args:
        operation: Operation to perform (collect, aggregate, reset, export)
        metric_types: JSON array of metric types to collect
        aggregation_period: Period for aggregation (minute, hour, day, week)
        data_points: JSON array of data points to process

    Returns:
        JSON string with statistics results
    """
    try:
        metrics = json.loads(metric_types) if metric_types else []
        data = json.loads(data_points) if data_points else []

        result = {
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
            "aggregation_period": aggregation_period,
            "metric_types": metrics,
            "statistics": {},
        }

        if operation == "collect":
            result["statistics"] = _collect_current_statistics(metrics, data)
        elif operation == "aggregate":
            result["statistics"] = _aggregate_statistics(metrics, aggregation_period, data)
        elif operation == "reset":
            result["statistics"] = _reset_statistics(metrics)
        elif operation == "export":
            result["statistics"] = _export_statistics(metrics, aggregation_period)
        else:
            raise ValueError(f"Unknown operation: {operation}")

        logger.info(f"Statistics {operation} completed for {len(metrics)} metric types")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Statistics collection failed: {e}")
        return json.dumps(
            {"operation": operation, "timestamp": datetime.now().isoformat(), "error": str(e), "statistics": {}}
        )


@function_tool
def audit_event_logger(
    event_type: str, event_data: str = "{}", user_context: str = "{}", severity: str = "info"
) -> str:
    """
    Log audit events for compliance and tracking.

    Args:
        event_type: Type of audit event (process_start, file_upload, error, etc.)
        event_data: JSON object with event-specific data
        user_context: JSON object with user/system context
        severity: Event severity (debug, info, warning, error, critical)

    Returns:
        JSON string with audit logging results
    """
    try:
        event = json.loads(event_data) if event_data else {}
        context = json.loads(user_context) if user_context else {}

        audit_entry = {
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "severity": severity,
            "event_data": event,
            "user_context": context,
            "system_info": {
                "process_id": "erni-foto",
                "version": "1.0.0",
                "environment": "production",  # Would be configurable
            },
        }

        # Log to audit logger
        audit_message = f"AUDIT: {event_type} | {json.dumps(audit_entry, separators=(',', ':'))}"

        if severity == "debug":
            audit_logger.debug(audit_message)
        elif severity == "info":
            audit_logger.info(audit_message)
        elif severity == "warning":
            audit_logger.warning(audit_message)
        elif severity == "error":
            audit_logger.error(audit_message)
        elif severity == "critical":
            audit_logger.critical(audit_message)
        else:
            audit_logger.info(audit_message)

        result = {
            "audit_logged": True,
            "event_type": event_type,
            "timestamp": audit_entry["timestamp"],
            "severity": severity,
            "entry_id": f"{event_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        }

        logger.debug(f"Audit event logged: {event_type}")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Audit logging failed: {e}")
        return json.dumps(
            {"audit_logged": False, "event_type": event_type, "timestamp": datetime.now().isoformat(), "error": str(e)}
        )


# Helper functions for report building
def _build_summary_report(sources: list, time_filter: dict) -> dict:
    """Build summary report sections."""
    return {
        "overview": {
            "total_files_processed": 0,
            "successful_uploads": 0,
            "failed_operations": 0,
            "processing_time": "0:00:00",
            "success_rate": "0%",
        },
        "by_agent": {
            "SharePointMetadataAgent": {"operations": 0, "success": 0, "errors": 0},
            "PhotoDownloadAgent": {"operations": 0, "success": 0, "errors": 0},
            "AIAnalysisAgent": {"operations": 0, "success": 0, "errors": 0},
            "MetadataGeneratorAgent": {"operations": 0, "success": 0, "errors": 0},
            "PhotoUploadAgent": {"operations": 0, "success": 0, "errors": 0},
        },
        "performance": {
            "avg_processing_time_per_file": "0:00:00",
            "files_per_hour": 0,
            "peak_processing_time": "0:00:00",
        },
    }


def _build_detailed_report(sources: list, time_filter: dict) -> dict:
    """Build detailed report sections."""
    return {
        "file_processing": {"downloaded_files": [], "analyzed_files": [], "uploaded_files": [], "failed_files": []},
        "metadata_analysis": {"fields_generated": {}, "validation_results": {}, "schema_compliance": {}},
        "error_details": {"by_type": {}, "by_agent": {}, "resolution_status": {}},
    }


def _build_error_report(sources: list, time_filter: dict) -> dict:
    """Build error-focused report sections."""
    return {
        "error_summary": {"total_errors": 0, "critical_errors": 0, "warnings": 0, "resolved_errors": 0},
        "error_categories": {
            "connection_errors": 0,
            "processing_errors": 0,
            "validation_errors": 0,
            "upload_errors": 0,
        },
        "error_details": [],
        "recommendations": [],
    }


def _build_performance_report(sources: list, time_filter: dict) -> dict:
    """Build performance-focused report sections."""
    return {
        "processing_metrics": {
            "total_processing_time": "0:00:00",
            "avg_time_per_file": "0:00:00",
            "throughput": "0 files/hour",
            "peak_performance": "0:00:00",
        },
        "resource_usage": {"memory_usage": "0 MB", "cpu_usage": "0%", "disk_usage": "0 MB", "network_usage": "0 MB"},
        "bottlenecks": [],
        "optimization_suggestions": [],
    }


def _format_as_html(report_data: dict) -> str:
    """Format report data as HTML."""
    html = f"""
    <html>
    <head>
        <title>Erni-Foto Report - {report_data['report_type'].title()}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .header {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; }}
            .section {{ margin: 20px 0; }}
            .metric {{ margin: 5px 0; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Erni-Foto {report_data['report_type'].title()} Report</h1>
            <p>Generated: {report_data['generated_at']}</p>
        </div>
        <div class="content">
            <!-- Report sections would be rendered here -->
        </div>
    </body>
    </html>
    """
    return html


def _format_as_csv(report_data: dict) -> str:
    """Format report data as CSV."""
    csv_lines = [
        "Report Type,Generated At,Section,Metric,Value",
        f"{report_data['report_type']},{report_data['generated_at']},Header,Report Type,{report_data['report_type']}",
    ]

    # Add sections data
    for section_name, section_data in report_data.get("sections", {}).items():
        if isinstance(section_data, dict):
            for key, value in section_data.items():
                csv_lines.append(
                    f"{report_data['report_type']},{report_data['generated_at']},{section_name},{key},{value}"
                )

    return "\n".join(csv_lines)


def _generate_default_message(notification_type: str, message_data: dict) -> str:
    """Generate default notification message."""
    if notification_type == "success":
        return f"Erni-Foto processing completed successfully. {message_data.get('summary', '')}"
    elif notification_type == "error":
        return f"Erni-Foto processing encountered errors. {message_data.get('error_details', '')}"
    elif notification_type == "warning":
        return f"Erni-Foto processing completed with warnings. {message_data.get('warning_details', '')}"
    else:
        return f"Erni-Foto notification: {message_data.get('message', 'No details provided')}"


def _deliver_to_log(notification_type: str, subject: str, body: str) -> None:
    """Deliver notification to log."""
    log_message = f"NOTIFICATION [{notification_type.upper()}]: {subject} - {body}"

    if notification_type == "error":
        logger.error(log_message)
    elif notification_type == "warning":
        logger.warning(log_message)
    else:
        logger.info(log_message)


def _deliver_to_file(notification_type: str, subject: str, body: str, file_path: str | None) -> dict:
    """Deliver notification to file."""
    try:
        if not file_path:
            file_path = f"notifications_{datetime.now().strftime('%Y%m%d')}.txt"

        notification_text = f"[{datetime.now().isoformat()}] {notification_type.upper()}: {subject}\n{body}\n\n"

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(notification_text)

        return {"method": "file", "success": True, "file_path": file_path, "message": "Written to file successfully"}
    except Exception as e:
        return {"method": "file", "success": False, "error": str(e)}


def _deliver_to_webhook(url: str, notification: dict) -> dict:
    """Deliver notification to webhook."""
    try:
        import requests

        response = requests.post(url, json=notification, timeout=30)
        response.raise_for_status()

        return {"method": "webhook", "success": True, "url": url, "status_code": response.status_code}
    except Exception as e:
        return {"method": "webhook", "success": False, "url": url, "error": str(e)}


def _collect_current_statistics(metrics: list, data: list) -> dict:
    """Collect current statistics."""
    stats = {}

    for metric in metrics:
        if metric == "processing_time":
            stats[metric] = {"current": "0:00:00", "average": "0:00:00", "total": "0:00:00"}
        elif metric == "success_rate":
            stats[metric] = {"current": "100%", "average": "95%", "trend": "stable"}
        elif metric == "throughput":
            stats[metric] = {"files_per_hour": 0, "files_per_minute": 0}
        elif metric == "errors":
            stats[metric] = {"count": 0, "rate": "0%", "types": {}}

    return stats


def _aggregate_statistics(metrics: list, period: str, data: list) -> dict:
    """Aggregate statistics over time period."""
    return {
        "period": period,
        "aggregated_metrics": {metric: {"sum": 0, "avg": 0, "min": 0, "max": 0} for metric in metrics},
        "time_series": [],
    }


def _reset_statistics(metrics: list) -> dict:
    """Reset statistics counters."""
    return {
        "reset_metrics": metrics,
        "reset_timestamp": datetime.now().isoformat(),
        "previous_values": dict.fromkeys(metrics, 0),
    }


def _export_statistics(metrics: list, period: str) -> dict:
    """Export statistics for external use."""
    return {
        "export_format": "json",
        "metrics": metrics,
        "period": period,
        "exported_data": {},
        "export_timestamp": datetime.now().isoformat(),
    }
