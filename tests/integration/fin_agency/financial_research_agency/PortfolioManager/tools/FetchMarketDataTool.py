import json

from pydantic import Field

from agency_swarm.tools import BaseTool


class FetchMarketDataTool(BaseTool):
    """
    Dummy tool for tests: returns a fixed market data output for any input.
    """

    symbol: str = Field(
        ...,
        description="Stock ticker symbol (e.g., 'AAPL', 'MSFT'). Must be 1-5 uppercase letters.",
    )

    def run(self):
        """
        Returns a dummy market data output for testing purposes.
        """
        # Always return the same dummy output for test stability
        result = {
            "symbol": self.symbol,
            "current_price": 202.38,
            "market_cap": "$3.006T",
            "pe_ratio": 30.28,
            "forward_pe": 28.5,
            "analyst_rating": "buy",
            "company_name": "Dummy Company Inc.",
            "sector": "Technology",
            "industry": "Dummy Industry",
        }
        return json.dumps(result, indent=2)


if __name__ == "__main__":
    tool = FetchMarketDataTool(symbol="AAPL")
    print(tool.run())
