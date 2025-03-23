# Agency-Swarm Fork Setup and Usage Guide

## Initial Setup

1. Fork Setup (Already Done)
- Forked VRSEN/agency-swarm to teamsigma1/agency-swarm
- Fork serves as central point for framework modifications

2. Create New Project
```bash
mkdir my_new_agency_project
cd my_new_agency_project
git init
git submodule add git@github.com:teamsigma1/agency-swarm.git
```

3. Set Up Upstream in Submodule
```bash
cd agency-swarm
git remote add upstream https://github.com/VRSEN/agency-swarm.git
```

4. Project Structure
```bash
python -m venv venv
source venv/bin/activate
pip install -e agency-swarm/

mkdir -p src/my_agency/{agents,tools,tools/rag}
touch src/my_agency/agency.py
touch src/my_agency/agency_manifesto.md
```

## Development Workflows

### Framework Modifications
```bash
cd agency-swarm
git checkout -b feature-name
# Make changes...
git commit -am "Feature description"
git push origin feature-name
```

### Update from Upstream
```bash
cd agency-swarm
git fetch upstream
git merge upstream/main
git push origin main
```

### RAG Implementation Example
```python
# src/my_agency/tools/rag/vector_store.py
from agency_swarm.tools import BaseTool
from pydantic import Field

class RAGTool(BaseTool):
    """RAG implementation for document processing and retrieval"""
    query: str = Field(..., description="Query to search in the document store")

    def run(self):
        # Your RAG implementation
        return "Retrieved context"
```

## Why This Structure?

1. **Centralized Control**
   - Your fork serves as the central hub for framework modifications
   - All projects use your fork as their source of truth

2. **Flexible Development**
   - Make framework changes in any project
   - Push important changes to your fork
   - Contribute selected improvements to upstream VRSEN/agency-swarm

3. **Clean Dependency Management**
   - Projects extend framework independently
   - Share common tools through the fork
   - Maintain private implementations in project repositories

4. **Update Flow**
   - VRSEN/agency-swarm → Your Fork → Your Projects
   - Pull upstream changes when ready
   - Projects update submodule reference when needed

5. **Contribution Flow**
   - Your Projects → Your Fork → VRSEN/agency-swarm
   - Develop and test in projects
   - Consolidate in fork
   - Submit PRs to main repository

## Usage Examples

1. **Fix Framework Bug**
```bash
cd my_new_agency_project/agency-swarm
git checkout -b fix-bug
# Make fixes
git commit -am "Fix description"
git push origin fix-bug
```

2. **Create New Tool**
   - Add tool in project
   - Test thoroughly
   - If needed across projects:
     Push to fork

3. **Update from Upstream**
```bash
cd agency-swarm
git fetch upstream
git merge upstream/main
git push origin main
```

4. **Update Project with Latest Fork Changes**
```bash
cd agency-swarm
git pull origin main
cd ..
git add agency-swarm
git commit -m "Update agency-swarm submodule"
```
