import json

from pydantic import Field

from agency_swarm.tools import BaseTool


class AnalyzeRiskFactorsTool(BaseTool):
    """
    Dummy tool for tests: returns a fixed risk analysis output for any input.
    """

    symbol: str = Field(..., description="Stock ticker symbol for risk analysis (e.g., 'AAPL', 'MSFT')")
    market_data: str = Field(
        ...,
        description="Current market data for the security including price and valuation metrics",
    )

    def run(self):
        """
        Returns a dummy risk assessment for testing purposes.
        """
        # Always return the same dummy output for test stability
        result = {
            "risk_level": "Moderate",
            "risk_score": "4/10",
            "key_risks": ["Dummy risk: This is a test output.", f"Symbol analyzed: {self.symbol}"],
            "recommendation": "This is a dummy recommendation for tests.",
            "volatility": "12.3%",
            "beta": 1.23,
            "pe_ratio": 21.0,
        }
        return json.dumps(result, indent=2)


if __name__ == "__main__":
    tool = AnalyzeRiskFactorsTool(symbol="AAPL", market_data="Price $202.38, P/E 30.28, Market Cap $3.006T")
    print(tool.run())
