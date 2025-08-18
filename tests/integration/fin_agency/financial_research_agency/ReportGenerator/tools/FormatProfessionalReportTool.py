import json
import re
from datetime import datetime

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class FormatProfessionalReportTool(BaseTool):
    """
    Transforms raw research data and analysis into professionally formatted investment reports
    with executive summary, detailed analysis sections, and clear recommendations suitable for client delivery.
    """

    content: str = Field(
        ...,
        description="Raw research content and analysis data to be formatted into a professional report",
    )
    report_type: str = Field(
        default="investment_analysis",
        description="Type of report: 'investment_analysis', 'risk_assessment', or 'market_overview'",
    )

    def run(self):
        """
        Formats the provided content into a structured professional investment report.
        Returns a JSON object containing all required sections for executive presentation.
        """
        try:
            # Validate report type
            valid_types = ["investment_analysis", "risk_assessment", "market_overview"]
            if self.report_type not in valid_types:
                return f"Error: Invalid report type. Must be one of: {', '.join(valid_types)}"

            # Extract symbol from content if present
            symbol_match = re.search(r"\b([A-Z]{1,5})\b", self.content)
            symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"

            # Parse market data from content
            price_match = re.search(r"\$(\d+\.?\d*)", self.content)
            current_price = price_match.group(1) if price_match else "N/A"

            # Parse risk information if present
            risk_level = "N/A"
            risk_score = "N/A"
            key_risks = []

            if "risk_level" in self.content.lower():
                risk_match = re.search(r'"risk_level":\s*"([^"]+)"', self.content)
                if risk_match:
                    risk_level = risk_match.group(1)

                score_match = re.search(r'"risk_score":\s*"([^"]+)"', self.content)
                if score_match:
                    risk_score = score_match.group(1)

                # Extract risk factors
                risks_match = re.search(r'"key_risks":\s*\[(.*?)\]', self.content, re.DOTALL)
                if risks_match:
                    risks_content = risks_match.group(1)
                    key_risks = [risk.strip().strip('"') for risk in risks_content.split(",") if risk.strip()]

            # Generate executive summary
            executive_summary = (
                f"This investment analysis provides a comprehensive evaluation of {symbol} "
                "based on current market conditions and risk assessment.\n"
                "The analysis incorporates market data, valuation metrics, risk factors, and "
                "competitive positioning to deliver actionable investment guidance.\n"
                f"Current market price stands at ${current_price} "
                f"with a risk assessment of {risk_level} level ({risk_score})."
            )

            # Generate market position analysis
            valuation_note = (
                "potential overvaluation concerns" if "high" in risk_level.lower() else "reasonable valuation levels"
            )

            company_fundamentals = "require careful monitoring" if risk_level == "High" else "appear stable"

            position_summary = (
                "challenged by elevated risk factors"
                if risk_level == "High"
                else "supported by manageable risk profile"
            )

            market_position = (
                f"{symbol} demonstrates the following market characteristics:\n"
                f"- Current trading price: ${current_price}\n"
                "- Market positioning reflects current sector dynamics and competitive landscape\n"
                f"- Valuation metrics indicate {valuation_note}\n"
                f"- Company fundamentals {company_fundamentals}\n\n"
                f"The security's market position is {position_summary}."
            )

            # Generate risk analysis summary
            risk_analysis = f"""
Risk Assessment Summary:
- Overall Risk Level: {risk_level}
- Risk Score: {risk_score}

Key Risk Factors Identified:
"""
            if key_risks:
                for i, risk in enumerate(key_risks[:5], 1):  # Limit to top 5 risks
                    risk_analysis += f"{i}. {risk}\n"
            else:
                risk_analysis += "No significant risk factors identified in the analysis."

            risk_assessment_phrase = (
                "heightened caution is warranted"
                if risk_level == "High"
                else "manageable risk levels for appropriate investment strategies"
            )

            risk_analysis += f"\nThe risk assessment indicates {risk_assessment_phrase}."

            # Generate final recommendation
            if risk_level == "High":
                final_recommendation = f"""
RECOMMENDATION: CAUTIOUS APPROACH
Given the high risk assessment ({risk_score}), we recommend:
- Consider reduced position sizing or avoiding investment
- Enhanced due diligence and monitoring if proceeding
- Portfolio diversification to mitigate concentration risk
- Regular review of risk factors and market conditions
"""
            elif risk_level == "Moderate":
                final_recommendation = f"""
RECOMMENDATION: MODERATE BUY with RISK MANAGEMENT
With moderate risk levels ({risk_score}), we recommend:
- Suitable for balanced investment portfolios
- Implement appropriate position sizing based on risk tolerance
- Monitor key risk factors regularly
- Consider as part of diversified investment strategy
"""
            else:
                final_recommendation = f"""
RECOMMENDATION: FAVORABLE INVESTMENT OPPORTUNITY
Low risk assessment ({risk_score}) supports:
- Suitable for conservative and growth-oriented portfolios
- Standard position sizing based on investment objectives
- Favorable risk-adjusted return potential
- Appropriate for long-term investment strategies
"""

            # Create structured report
            report = {
                "executive_summary": executive_summary.strip(),
                "market_position": market_position.strip(),
                "risk_analysis": risk_analysis.strip(),
                "final_recommendation": final_recommendation.strip(),
                "report_metadata": {
                    "symbol": symbol,
                    "report_type": self.report_type,
                    "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "risk_level": risk_level,
                    "current_price": current_price,
                },
            }

            return json.dumps(report, indent=2)

        except Exception as e:
            return f"Error formatting professional report: {str(e)}"


if __name__ == "__main__":
    sample_content = """Retrieved market data for AAPL: Price $202.38, Market Cap $3.006T, P/E 30.28
    Risk analysis shows moderate risk level with score 4/10"""

    tool = FormatProfessionalReportTool(content=sample_content, report_type="investment_analysis")
    print(tool.run())
