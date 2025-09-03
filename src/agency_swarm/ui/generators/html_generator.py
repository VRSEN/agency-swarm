"""
HTML visualization generator for Agency Swarm.

This module provides HTML visualization generation
using templates.
"""

import json
import webbrowser
from pathlib import Path
from typing import Any


class HTMLVisualizationGenerator:
    """
    Generates HTML visualizations for Agency Swarm agencies.
    Uses templates for HTML generation.
    """

    def __init__(self):
        self.template_dir = Path(__file__).parents[1] / "templates" / "html"

    def generate_interactive_html(
        self,
        agency_data: dict[str, Any],
        output_file: str = "agency_visualization.html",
        open_browser: bool = True,
    ) -> str:
        """
        Generate a complete interactive HTML visualization.

        Args:
            agency_data: The agency structure data from get_agency_structure()
            output_file: Path to save the HTML file
            open_browser: Whether to automatically open in browser

        Returns:
            Path to the generated HTML file
        """
        # Apply hierarchical layout to the data
        from ..core.layout_algorithms import LayoutAlgorithms

        positioned_data = LayoutAlgorithms.apply_layout(agency_data, width=800, height=600)

        # Load templates
        html_template = self._load_template("visualization.html")
        css_content = self._load_template("styles.css")
        js_content = self._load_template("visualization.js")

        # Prepare template variables
        agency_name = positioned_data.get("metadata", {}).get("agencyName", "Agency Swarm Visualization")
        agency_json = json.dumps(positioned_data, indent=2)

        # Replace placeholders in HTML template
        html_content = html_template.replace("{{ agency_name }}", agency_name)
        html_content = html_content.replace("{AGENCY_DATA_PLACEHOLDER}", agency_json)

        # Embed CSS and JS directly for standalone HTML file
        html_content = html_content.replace(
            '<link rel="stylesheet" href="styles.css">', f"<style>\n{css_content}\n</style>"
        )
        html_content = html_content.replace(
            '<script src="visualization.js"></script>', f"<script>\n{js_content}\n</script>"
        )

        # Write the complete HTML file
        output_path = Path(output_file).resolve()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Open in browser if requested
        if open_browser:
            self._open_in_browser(output_path)

        return str(output_path)

    def generate_component_files(
        self,
        agency_data: dict[str, Any],
        output_dir: str = "agency_visualization",
    ) -> dict[str, str]:
        """
        Generate separate HTML, CSS, and JS files for web development.

        Args:
            agency_data: The agency structure data
            output_dir: Directory to save the files

        Returns:
            Dictionary with paths to generated files
        """
        # Apply hierarchical layout
        from ..core.layout_algorithms import LayoutAlgorithms

        positioned_data = LayoutAlgorithms.apply_layout(agency_data, width=800, height=600)

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Generate individual files
        files = {}

        # HTML file
        html_template = self._load_template("visualization.html")
        agency_name = positioned_data.get("metadata", {}).get("agencyName", "Agency Swarm Visualization")
        agency_json = json.dumps(positioned_data, indent=2)

        html_content = html_template.replace("{{ agency_name }}", agency_name)
        html_content = html_content.replace("{AGENCY_DATA_PLACEHOLDER}", agency_json)

        html_file = output_path / "index.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        files["html"] = str(html_file)

        # CSS file
        css_content = self._load_template("styles.css")
        css_file = output_path / "styles.css"
        with open(css_file, "w", encoding="utf-8") as f:
            f.write(css_content)
        files["css"] = str(css_file)

        # JS file
        js_content = self._load_template("visualization.js")
        js_file = output_path / "visualization.js"
        with open(js_file, "w", encoding="utf-8") as f:
            f.write(js_content)
        files["js"] = str(js_file)

        return files

    def _load_template(self, template_name: str) -> str:
        """Load a template file."""
        template_path = self.template_dir / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        with open(template_path, encoding="utf-8") as f:
            return f.read()

    def _open_in_browser(self, file_path: Path) -> None:
        """Open the HTML file in the default browser."""
        try:
            webbrowser.open(f"file://{file_path}")
        except Exception as e:
            print(f"Could not open browser automatically: {e}")
            print(f"Please open this file manually: {file_path}")

    @staticmethod
    def create_visualization_from_agency(
        agency,
        output_file: str = "agency_visualization.html",
        include_tools: bool = True,
        open_browser: bool = True,
    ) -> str:
        """
        Convenience method to create visualization directly from an Agency instance.

        Args:
            agency: The Agency instance
            output_file: Path to save the HTML file
            include_tools: Whether to include tools in visualization
            open_browser: Whether to open in browser

        Returns:
            Path to the generated HTML file
        """
        # Get agency structure data
        agency_data = agency.get_agency_structure(include_tools=include_tools)

        # Generate HTML
        generator = HTMLVisualizationGenerator()
        return generator.generate_interactive_html(
            agency_data=agency_data,
            output_file=output_file,
            open_browser=open_browser,
        )
