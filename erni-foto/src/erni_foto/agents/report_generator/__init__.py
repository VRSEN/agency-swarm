"""
Report Generator Agent for Erni-Foto system.

This agent handles comprehensive reporting and monitoring, including:
- Real-time progress monitoring and statistics
- Comprehensive processing reports and audit trails
- Error tracking and analysis
- Performance metrics and optimization insights
"""

from .agent import ReportGeneratorAgent
from .tools import audit_event_logger, notification_sender, report_builder, statistics_collector

__all__ = [
    "ReportGeneratorAgent",
    "report_builder",
    "notification_sender",
    "statistics_collector",
    "audit_event_logger",
]
