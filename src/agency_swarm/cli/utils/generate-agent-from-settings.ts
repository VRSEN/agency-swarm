#!/usr/bin/env node

/**
 * Script to generate Agency Swarm v1.x agent from settings.json file.
 *
 * Usage:
 *   npx ts-node generate-agent-from-settings.ts <settings.json>
 *   OR
 *   node generate-agent-from-settings.js <settings.json>
 *
 * This will create a single agent folder in the current directory.
 */

import * as fs from 'fs';
import * as path from 'path';

interface ToolResources {
  file_search?: {
    vector_store_ids?: string[];
  };
  code_interpreter?: {
    file_ids?: string[];
  };
}

interface AgentSettings {
  id?: string;
  name: string;
  description: string;
  instructions: string;
  model: string;
  temperature?: number;
  top_p?: number;
  reasoning_effort?: string;
  response_format?: any;
  tools?: any[];
  tool_resources?: ToolResources;
}


/**
 * Map JSON schema types to Python types.
 */
function mapJsonTypeToPython(jsonType: string): string {
  const typeMap: { [key: string]: string } = {
    'string': 'str',
    'integer': 'int',
    'number': 'float',
    'boolean': 'bool',
    'array': 'list',
    'object': 'dict'
  };
  return typeMap[jsonType] || 'Any';
}

/**
 * Generate Pydantic model class from JSON schema.
 */
function generatePydanticModel(schema: any, className: string): string {
  const properties = schema.schema_?.properties || schema.properties || {};
  const required = schema.schema_?.required || schema.required || [];

  let modelClass = `class ${className}(BaseModel):\n`;

  for (const [fieldName, fieldDef] of Object.entries(properties)) {
    const field = fieldDef as any;

    // Map the type
    const pythonType = mapJsonTypeToPython(field.type || 'string');

    // Check if field is required
    const isRequired = required.includes(fieldName);

    // Build Field parameters dynamically from all available properties
    const fieldParams: string[] = [];

    // Add all field properties except 'type' (which becomes the Python type)
    for (const [key, value] of Object.entries(field)) {
      if (key !== 'type' && value !== undefined && value !== null) {
        if (typeof value === 'string') {
          fieldParams.push(`${key}="${value}"`);
        } else if (typeof value === 'boolean') {
          fieldParams.push(`${key}=${value ? 'True' : 'False'}`);
        } else if (typeof value === 'number') {
          fieldParams.push(`${key}=${value}`);
        } else if (Array.isArray(value)) {
          fieldParams.push(`${key}=${toPythonObject(value)}`);
        } else if (typeof value === 'object') {
          fieldParams.push(`${key}=${toPythonObject(value)}`);
        }
      }
    }

    // Generate the field definition
    if (isRequired && fieldParams.length > 0) {
      modelClass += `    ${fieldName}: ${pythonType} = Field(${fieldParams.join(', ')})\n`;
    } else if (isRequired) {
      modelClass += `    ${fieldName}: ${pythonType}\n`;
    } else if (fieldParams.length > 0) {
      modelClass += `    ${fieldName}: ${pythonType} = Field(default=None, ${fieldParams.join(', ')})\n`;
    } else {
      modelClass += `    ${fieldName}: ${pythonType} = None\n`;
    }
  }

  return modelClass;
}

/**
 * Convert JavaScript object to Python-compatible string representation.
 */
function toPythonObject(obj: any): string {
  if (obj === null) return 'None';
  if (obj === true) return 'True';
  if (obj === false) return 'False';
  if (typeof obj === 'string') return JSON.stringify(obj);
  if (typeof obj === 'number') return obj.toString();
  if (Array.isArray(obj)) {
    return '[' + obj.map(item => toPythonObject(item)).join(', ') + ']';
  }
  if (typeof obj === 'object') {
    const pairs = Object.entries(obj).map(([key, value]) =>
      `"${key}": ${toPythonObject(value)}`
    );
    return '{' + pairs.join(', ') + '}';
  }
  return JSON.stringify(obj);
}

/**
 * Convert agent name to valid Python module name.
 */
function sanitizeName(name: string): string {
  // Replace spaces with underscores
  let sanitized = name.replace(/\s+/g, '_');

  // Remove other special characters (but keep letters, numbers, underscores)
  sanitized = sanitized.replace(/[^a-zA-Z0-9_]/g, '');

  // Remove multiple underscores
  sanitized = sanitized.replace(/_+/g, '_');

  // Remove leading/trailing underscores
  sanitized = sanitized.replace(/^_+|_+$/g, '');

  // If starts with digit, prepend 'agent_'
  if (/^\d/.test(sanitized)) {
    sanitized = 'agent_' + sanitized;
  }

  // Ensure it's not empty
  if (!sanitized) {
    sanitized = 'agent';
  }

  return sanitized;
}


/**
 * Generate instructions.md content from agent settings.
 */
function generateInstructionsMd(agentData: AgentSettings): string {
  return agentData.instructions || '';
}

/**
 * Generate the main agent.py file.
 */
function generateAgentPy(agentData: AgentSettings, agentName: string): string {
  const displayName = agentData.name;
  const pythonDisplayName = toPythonObject(displayName);

  // Build optional agent parameters
  let optionalParams = '';

  if (agentData.description) {
    optionalParams += `    description=${toPythonObject(agentData.description)},\n`;
  }

  // Handle response_format for JSON output
  let pydanticModelClass = '';
  if (agentData.response_format && agentData.response_format !== "auto") {
    if (agentData.response_format === "json_object" ||
        (typeof agentData.response_format === "object" && agentData.response_format.type === "json_object")) {
      // For JSON object output, use AgentOutputSchema with dict[str, Any]
      optionalParams += `    output_type=AgentOutputSchema(dict[str, Any], strict_json_schema=False),\n`;
      optionalParams += `    validation_attempts=5,\n`;
    } else if (typeof agentData.response_format === "object" &&
               agentData.response_format.type === "json_schema" &&
               agentData.response_format.json_schema) {
      // For JSON schema, create a Pydantic model class
      const schema = agentData.response_format.json_schema;
      const className = schema.name || 'OutputModel';

      pydanticModelClass = generatePydanticModel(schema, className);
      optionalParams += `    output_type=${className},\n`;
    } else {
      // Convert to Python-compatible format
      const pythonCompatibleJson = toPythonObject(agentData.response_format);
      optionalParams += `    output_type=${pythonCompatibleJson},\n`;
    }
  }

  // Extract built-in tools from the tools array and create proper Tool objects
  const toolImports: string[] = [];
  const toolInstances: string[] = [];

  if (agentData.tools) {
    for (const tool of agentData.tools) {
      if (tool.type === "file_search") {
        toolImports.push("FileSearchTool");

        // Configure FileSearchTool with all available parameters
        let fileSearchConfig = "FileSearchTool(";
        const configParts: string[] = [];

        if (agentData.tool_resources?.file_search?.vector_store_ids?.length) {
          const vectorStoreIds = agentData.tool_resources.file_search.vector_store_ids
            .map(id => `"${id}"`)
            .join(', ');
          configParts.push(`vector_store_ids=[${vectorStoreIds}]`);
        }

        // Add max_num_results if present in the tool definition
        if (tool.file_search?.max_num_results !== undefined) {
          configParts.push(`max_num_results=${tool.file_search.max_num_results}`);
        }


        // Add ranking_options if present in the tool definition
        if (tool.file_search?.ranking_options) {
          const rankingOptions = tool.file_search.ranking_options;
          let rankingConfig = "ranking_options=RankingOptions(";
          const rankingParts: string[] = [];

          // Always set ranker to "auto" because published ranker names change frequently
          rankingParts.push(`ranker="auto"`);

          if (rankingOptions.score_threshold !== undefined) {
            rankingParts.push(`score_threshold=${rankingOptions.score_threshold}`);
          }

          rankingConfig += rankingParts.join(', ') + ")";
          configParts.push(rankingConfig);

          // Add RankingOptions to imports
          if (!toolImports.includes("RankingOptions")) {
            toolImports.push("RankingOptions");
          }
        }

        // Add filters if present (would need Filters import too)
        if (tool.file_search?.filters) {
          configParts.push(`filters=${toPythonObject(tool.file_search.filters)}`);
          // Add Filters to imports
          if (!toolImports.includes("Filters")) {
            toolImports.push("Filters");
          }
        }

        fileSearchConfig += configParts.join(', ') + ")";
        toolInstances.push(fileSearchConfig);
      } else if (tool.type === "code_interpreter") {
        toolImports.push("CodeInterpreterTool");

        // Configure CodeInterpreterTool with proper structure
        const fileIds = agentData.tool_resources?.code_interpreter?.file_ids || [];
        const fileIdsStr = fileIds.map(id => `"${id}"`).join(', ');

        const codeInterpreterConfig = `CodeInterpreterTool(
            tool_config=CodeInterpreter(
                container=CodeInterpreterContainerCodeInterpreterToolAuto(type="auto", file_ids=[${fileIdsStr}]),
                type="code_interpreter",
            )
        )`;

        toolInstances.push(codeInterpreterConfig);
      }
    }
  }

  if (toolInstances.length > 0) {
    optionalParams += `    tools=[${toolInstances.join(', ')}],\n`;
  }

  // Add model as direct parameter if provided
  if (agentData.model) {
    optionalParams += `    model=${toPythonObject(agentData.model)},\n`;
  }

  // Build ModelSettings - only if we have model settings to include (excluding model)
  let modelSettingsBlock = '';
  let modelSettingsParams: string[] = [];

  if (agentData.temperature !== undefined) {
    modelSettingsParams.push(`temperature=${agentData.temperature}`);
  }

  if (agentData.top_p !== undefined) {
    modelSettingsParams.push(`top_p=${agentData.top_p}`);
  }

  if (agentData.reasoning_effort) {
    modelSettingsParams.push(`reasoning=Reasoning(effort="${agentData.reasoning_effort}")`);
  }

  // Only include ModelSettings if we have parameters for it
  if (modelSettingsParams.length > 0) {
    const formattedParams = modelSettingsParams.join(',\n        ');
    modelSettingsBlock = `    model_settings=ModelSettings(
        ${formattedParams}
    ),\n`;
  }

  // Determine imports
  let imports = `from agency_swarm import Agent`;
  if (modelSettingsParams.length > 0) {
    imports += `, ModelSettings`;
  }

  // Check if AgentOutputSchema is needed for JSON output
  const needsAgentOutputSchema = agentData.response_format &&
    (agentData.response_format === "json_object" ||
     (typeof agentData.response_format === "object" && agentData.response_format.type === "json_object"));

  // Check if Pydantic imports are needed for JSON schema
  const needsPydantic = agentData.response_format &&
    typeof agentData.response_format === "object" &&
    agentData.response_format.type === "json_schema";

  if (needsAgentOutputSchema) {
    imports = `from typing import Any\nfrom agents.agent_output import AgentOutputSchema\n` + imports;
  } else if (needsPydantic) {
    imports = `from pydantic import BaseModel, Field\n` + imports;
  }
  if (agentData.reasoning_effort) {
    imports += `\nfrom openai.types.shared import Reasoning`;
  }
  if (toolImports.length > 0) {
    // Separate RankingOptions and Filters from regular agent tools
    const agentTools = toolImports.filter(tool => !['RankingOptions', 'Filters'].includes(tool));
    const openaiTools = toolImports.filter(tool => ['RankingOptions', 'Filters'].includes(tool));

    if (agentTools.length > 0) {
      imports += `\nfrom agents import ${agentTools.join(', ')}`;
    }

    if (openaiTools.includes('RankingOptions')) {
      imports += `\nfrom openai.types.responses.file_search_tool_param import RankingOptions`;
    }

    if (openaiTools.includes('Filters')) {
      imports += `\nfrom openai.types.responses.file_search_tool_param import Filters`;
    }
  }

  // Check if CodeInterpreter is needed and add separate import
  const needsCodeInterpreter = agentData.tools?.some(tool => tool.type === "code_interpreter");
  if (needsCodeInterpreter) {
    imports += `\nfrom openai.types.responses.tool_param import CodeInterpreter, CodeInterpreterContainerCodeInterpreterToolAuto`;
  }

  const content = `${imports}

${pydanticModelClass}${pydanticModelClass ? '\n' : ''}${agentName} = Agent(
    name=${pythonDisplayName},
    instructions="./instructions.md",
${optionalParams}${modelSettingsBlock})

if __name__ == "__main__":
    from agency_swarm import Agency
    agency = Agency(${agentName})
    print(agency.get_response_sync("What's your name?"))
`;

  return content;
}

/**
 * Generate __init__.py for the agent.
 */
function generateInitPy(agentName: string, displayName: string): string {
  return `from .${agentName} import ${agentName}

__all__ = ["${agentName}"]
`;
}

/**
 * Main function to generate agent from settings.json.
 */
function main(): void {
  const args = process.argv.slice(2);

  if (args.length !== 1) {
    console.log('Usage: npx ts-node generate-agent-from-settings.ts <settings.json>');
    process.exit(1);
  }

  const settingsFile = args[0];

  if (!fs.existsSync(settingsFile)) {
    console.log(`Error: Settings file '${settingsFile}' not found.`);
    process.exit(1);
  }

  let settingsData: any;

  try {
    const fileContent = fs.readFileSync(settingsFile, 'utf8');
    settingsData = JSON.parse(fileContent);
  } catch (error) {
    if (error instanceof SyntaxError) {
      console.log(`Error: Invalid JSON in settings file: ${error.message}`);
    } else {
      console.log(`Error reading settings file: ${error}`);
    }
    process.exit(1);
  }

  // Handle both single agent object and array of agents
  let agentsList: AgentSettings[];

  if (Array.isArray(settingsData)) {
    if (settingsData.length === 0) {
      console.log('Error: Empty agent list in settings file.');
      process.exit(1);
    }
    agentsList = settingsData;
    console.log(`Found ${agentsList.length} agent(s) to generate.`);
  } else {
    agentsList = [settingsData];
  }

  const generatedAgents: string[] = [];

  // Process each agent
  for (let i = 0; i < agentsList.length; i++) {
    const agentData = agentsList[i];

    // Extract agent information
    const displayName = agentData.name || `Agent${i + 1}`;
    const agentName = sanitizeName(displayName);

    console.log(`\n[${i + 1}/${agentsList.length}] Generating agent: ${displayName} -> ${agentName}`);

    // Create agent directory
    const agentDir = agentName;
    if (fs.existsSync(agentDir)) {
      console.log(`Warning: Directory '${agentName}' already exists. Files will be overwritten.`);
    }

    if (!fs.existsSync(agentDir)) {
      fs.mkdirSync(agentDir, { recursive: true });
    }

    // Generate files
    try {
      // Generate instructions.md
      const instructionsContent = generateInstructionsMd(agentData);
      fs.writeFileSync(path.join(agentDir, 'instructions.md'), instructionsContent, 'utf8');

      // Generate agent.py
      const agentContent = generateAgentPy(agentData, agentName);
      fs.writeFileSync(path.join(agentDir, `${agentName}.py`), agentContent, 'utf8');

      // Generate __init__.py
      const initContent = generateInitPy(agentName, displayName);
      fs.writeFileSync(path.join(agentDir, '__init__.py'), initContent, 'utf8');

      console.log(`Successfully generated agent '${displayName}' in directory '${agentName}/'`);
      generatedAgents.push(agentName);

    } catch (error) {
      console.log(`Error generating agent '${displayName}': ${error}`);
      process.exit(1);
    }
  }

  // Summary
  console.log(`\n=== Generation Complete ===`);
  console.log(`Generated ${generatedAgents.length} agent(s):`);
  generatedAgents.forEach((agentName, index) => {
    console.log(`  ${index + 1}. ${agentName}/`);
    console.log(`     - ${agentName}.py`);
    console.log(`     - instructions.md`);
    console.log(`     - __init__.py`);
  });

  console.log(`\n* Review and customize agent configurations as needed.`);
}

// Run the script if called directly
if (require.main === module) {
  main();
}

export {
  sanitizeName,
  generateInstructionsMd,
  generateAgentPy,
  generateInitPy,
  main
};
