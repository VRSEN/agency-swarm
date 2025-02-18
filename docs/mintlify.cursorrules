Mintlify Docs Cheatsheet

# General

Start each page with a metadata block:

```mdx
---
title: "Page Title"
description: "Brief description of the page"
icon: "icon-name"
---
```

# Getting Started

## Global Settings (`mint.json`)

Your Mintlify site requires a `mint.json` file containing core configurations.

### Key Properties

#### Styling

- **name** (`string`, required): Your company or project name.
- **logo** (`string` or `Logo`, optional): Path to logo image(s).
  - For example:
    ```json
    "logo": "/path/to/logo.svg"
    ```
  - For light/dark modes:
    ```json
    "logo": {
      "light": "/path/to/light-logo.svg",
      "dark": "/path/to/dark-logo.svg",
      "url": "/"
    }
    ```
- **favicon** (`string`, optional): Path to your favicon image.
- **colors** (`Colors`, optional): Hex color codes for your theme.
- **theme** (`"venus"` | `"quill"` | `"prism"`, optional): Preset theme configurations.
- **layout** (`"topnav"` | `"sidenav"` | `"solidSidenav"`, optional): Global layout style.
- **background** (`Background`, optional): Decorative background settings.
- **font** (`FontDetailsType` or `{ headings?: FontDetailsType, body?: FontDetailsType }`, optional): Custom fonts.
- **modeToggle** (`ModeToggle`, optional): Customize the dark mode toggle.
- **sidebar** (`Sidebar`, optional): Customize sidebar components.
- **topbar** (`Topbar`, optional): Styling for the topbar.
- **search** (`Search`, optional): Configure the search bar location.
- **rounded** (`"default"` | `"sharp"`, optional): Style of rounded edges in the UI.
- **codeBlock** (`CodeBlock`, optional): Style code blocks in the documentation.

#### Structure

- **navigation** (`Navigation[]`, required): Define your site's navigation structure.
  ```json
  "navigation": [
    {
      "group": "Getting Started",
      "pages": ["quickstart"]
    }
  ]
  ```
- **topbarLinks** (`TopbarLink[]`, optional): Links to include in the topbar.
  ```json
  "topbarLinks": [
    {
      "name": "Community",
      "url": "https://mintlify.com/community"
    }
  ]
  ```
- **topbarCtaButton** (`Call to Action`, optional): Configuration for the topbar CTA button.
  ```json
  "topbarCTA": {
    "name": "Get Started",
    "url": "https://mintlify.com/get-started"
  }
  ```
- **versions** (`string[]`, optional): Doc versions for localization or versioning.
- **anchors** (`Anchor[]`, optional): Anchors for quick links to sections or external URLs.
- **topAnchor** (`Anchor`, optional): Override the default top anchor.
- **tabs** (`Tabs[]`, optional): Navigational tabs.
  ```json
  "tabs": [
    {
      "name": "API References",
      "url": "api-references"
    },
    {
      "name": "Content",
      "url": "content"
    }
  ],
  "primaryTab": {
    "name": "Home"
  }
  ```
- **footer** (`FooterSocials`, `FooterLinksColumn[]`, optional): Configure footer socials and links.
- **feedback** (`Feedback`, optional): Enable feedback buttons.

#### API Configurations

- **api** (`API`, optional): API settings configuration.
- **openapi** (`string` | `string[]`, optional): Paths or URLs to your OpenAPI files.
  ```json
  "openapi": "https://example.com/openapi.json"
  ```
  Or multiple OpenAPI files:
  ```json
  "openapi": [
    "https://example.com/openapi1.json",
    "./path/to/openapi2.json"
  ]
  ```
- **integrations** (`Integrations`, optional): Third-party integrations (excluding analytics).
- **analytics** (`Analytics`, optional): Third-party analytics integrations.

#### Redirects

- **redirects** (`Redirect[]`, optional): Configure URL redirects.
  ```json
  "redirects": [
    {
      "source": "/old-path",
      "destination": "/new-path"
    }
  ]
  ```

#### SEO

- **seo** (`SEO`, optional): Search Engine Optimization settings.
  - **indexHiddenPages** (`boolean`, default `false`): Index pages not included in navigation.
  ```json
  "seo": {
    "indexHiddenPages": true
  }
  ```

---

# Writing Content

## Page Titles and Metadata

Begin each MDX page with metadata:

```mdx
---
title: "Page Title"
description: "Brief description of the page"
icon: "icon-name"
---
```

### Additional Metadata Options

- **sidebarTitle**: Display a different title in the sidebar.
  ```mdx
  ---
  title: "Long Page Title"
  sidebarTitle: "Short Title"
  ---
  ```
- **icon** and **iconType**: Include icons for sidebar items.
  ```mdx
  ---
  title: "Code Block"
  icon: "rectangle-code"
  iconType: "solid"
  ---
  ```
- **mode**: Customize page layout.
  - `"default"`: Standard layout with table of contents.
  - `"wide"`: Hide the table of contents.
  - `"custom"`: Minimalist layout with only the top bar.
  ```mdx
  ---
  mode: "wide"
  ---
  ```
- **url**: Create external links in the sidebar.
  ```mdx
  ---
  title: "External Resource"
  url: "https://www.example.com"
  ---
  ```

## Content Formatting

### Headers

Structure your content with headers:

```markdown
## Title (H2)
### Subtitle (H3)
```

### Text Formatting

- **Bold**: `**text**` → **text**
- *Italic*: `_text_` → _text_
- ~~Strikethrough~~: `~text~` → ~~text~~

### Links

- **External**: `[Link Text](https://example.com)`
- **Internal**: `[Link Text](/path/to/page)`

### Images

- **Markdown Syntax**:
  ```markdown
  ![Alt Text](/path/image.jpg)
  ```
- **Disable Zoom**:
  ```html
  <img src="/path/image.jpg" noZoom />
  ```
- **Linking Images**:
  ```html
  <a href="https://website.com" target="_blank">
    <img src="/path/image.jpg" />
  </a>
  ```

### Code Blocks

- **Inline Code**: `` `code` ``
- **Fenced Code Blocks**:
  ```language
  // Code here
  ```
- **Named Code Blocks**:
  ```javascript Example.js
  // JavaScript code
  ```
- **Line Highlighting**:
  ```javascript {1,3-5}
  // Code with specific lines highlighted
  ```
- **Code Groups**:
  ```mdx
  <CodeGroup>
    ```python example.py
    # Python code
    ```
    ```javascript example.js
    // JavaScript code
    ```
  </CodeGroup>
  ```

---

# Components

## Accordion

Create collapsible sections:

```mdx
<Accordion title="Section Title">
  Content inside the accordion.
</Accordion>
```

- **Props**:
  - `title` (string): Title displayed on the accordion.
  - `defaultOpen` (boolean): If `true`, accordion is open by default.

## Tabs

Switch between different content sections:

```mdx
<Tabs>
  <Tab title="First Tab">
    Content for the first tab.
  </Tab>
  <Tab title="Second Tab">
    Content for the second tab.
  </Tab>
</Tabs>
```

## Cards

Highlight key points or links:

```mdx
<Card title="Card Title" icon="icon-name" href="/link">
  Card content goes here.
</Card>
```

- **Props**:
  - `title` (string): Title of the card.
  - `icon` (string): Font Awesome icon name (examples: address-book, at, clipboard-user, code, database, eye, file-code, file-csv, file-lines, file-pdf, file-word, file-xml, fire-flame, folder-tree, folders, gear-code, github, globe-pointer, globe-stand, google, image, magnifying-glass-location, markdown, people-group, rocket-launch, screen-users, screwdriver-wrench, signal-stream, spider-web, terminal, toolbox, wrench, youtube).
  - `href` (string): URL to navigate when card is clicked.
  - `horizontal` (boolean): Display card in horizontal layout.
  - `img` (string): Path to an image displayed on the card.

## Steps

Display step-by-step instructions:

```mdx
<Steps>
  <Step title="Step One">
    Instructions for step one.
  </Step>
  <Step title="Step Two">
    Instructions for step two.
  </Step>
</Steps>
```

## Tooltips

Show additional information on hover:

```mdx
<Tooltip tip="Tooltip text">Hover over this text</Tooltip>
```

---

# API Components

## ParamField

Define API parameters:

```mdx
<ParamField param="user_id" type="string" required>
  The unique identifier of the user.
</ParamField>
```

- **Props**:
  - `param` (string): Parameter name.
  - `type` (string): Data type.
  - `required` (boolean): Indicates if parameter is required.
  - `default` (string): Default value.
  - `placeholder` (string): Placeholder text.
  - `deprecated` (boolean): Indicates if parameter is deprecated.

## ResponseField

Define API response fields:

```mdx
<ResponseField name="status" type="string" required>
  Status of the response.
</ResponseField>
```

- **Props**:
  - `name` (string): Field name.
  - `type` (string): Data type.
  - `required` (boolean): Indicates if field is required.
  - `default` (string): Default value.

## Expandable

Toggle the display of nested fields:

```mdx
<Expandable title="User Object">
  <ResponseField name="id" type="string">User ID</ResponseField>
  <ResponseField name="email" type="string">User Email</ResponseField>
</Expandable>
```

---

# Sidebar Code Examples

Use `<RequestExample>` and `<ResponseExample>` to display code in the sidebar.

```mdx
<RequestExample>
  ```javascript Example Request
  fetch('https://api.example.com/users')
    .then(response => response.json())
    .then(data => console.log(data));
  ```
</RequestExample>

<ResponseExample>
  ```json
  {
    "users": [
      { "id": "1", "name": "Alice" },
      { "id": "2", "name": "Bob" }
    ]
  }
  ```
</ResponseExample>
```

---

# Diagrams

## Mermaid Diagrams

Create diagrams using Mermaid syntax:

```markdown
```mermaid
graph TD
  A[Start] --> B[Process]
  B --> C[End]
```
```

---

This cheatsheet provides practical guidance for using Mintlify to create documentation sites with various components and configurations.
