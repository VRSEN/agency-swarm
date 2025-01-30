# Social Media Agency Architecture

## System Overview
The agency-swarm is a multi-agent system designed to automate the process of creating viral social media content from long-form videos. The system uses AI to identify high-impact moments, enhance them with creative elements, and optimize them for various social media platforms.

## Agent Hierarchy
1. CEO Agent (AgencyCEO)
   - Oversees workflow
   - Manages inter-agent communication
   - Sets revenue targets
   
2. Content Acquisition Agent
   - Tools: YouTube API wrapper, yt-dlp integration
   - Responsibilities: 
     - Download full episodes
     - Monitor new uploads
     - Extract subtitles and metadata
   - Implementation:
     - Uses yt-dlp for reliable video downloads
     - Integrates with YouTube Data API v3 for channel monitoring
     - Supports automatic subtitle extraction
   
3. Analysis Agent
   - Tools: Whisper transcription, GPT-4-Temporal for video analysis
   - Responsibilities: 
     - Identify high-impact moments using:
       - Emotional intensity detection
       - Keyword density analysis
       - Visual action scoring
   - Implementation:
     - Uses OpenAI Whisper for accurate transcription
     - Implements custom scoring algorithms for moment detection
     
4. Creative Agent
   - Tools: Runway ML, D-ID, ElevenLabs
   - Responsibilities:
     - Create animated versions of key moments
     - Generate side-by-side layouts with FFmpeg
     - Add dynamic captions with MoviePy
   - Implementation:
     - Integrates with FFmpeg for video processing
     - Uses MoviePy for Python-based video editing
     
5. Production Agent
   - Tools: AWS MediaConvert, Deepbrain AI
   - Responsibilities:
     - Render final videos
     - Optimize for vertical format
     - Add viral hooks/CTAs
   
6. Publishing Agent
   - Tools: YouTube API, TubeBuddy integration
   - Responsibilities:
     - SEO-optimized titles/descriptions
     - Strategic scheduling
     - Comment engagement
   
7. Analytics Agent
   - Tools: YouTube Analytics API, SocialBlade
   - Responsibilities:
     - A/B test different versions
     - Revenue tracking
     - Retention analysis

## Technical Implementation

### Base Components
1. Base Agent Class
   - Provides common functionality for all agents
   - Implements logging and configuration management
   - Handles inter-agent communication

2. Configuration Management
   - Environment-based configuration
   - Agent-specific settings
   - API key management

3. Tool Integration
   - Modular tool system
   - Easy integration of new APIs
   - Error handling and retry logic

### Data Flow
1. Content Acquisition
   ```
   YouTube Video -> Download -> Subtitle Extraction -> Local Storage
   ```

2. Analysis Pipeline
   ```
   Video + Subtitles -> Transcription -> Moment Detection -> Scoring -> Selection
   ```

3. Production Pipeline
   ```
   Selected Moments -> Enhancement -> Rendering -> Format Optimization -> Publishing
   ```

### Storage
1. Local Storage
   - Downloaded videos
   - Extracted subtitles
   - Intermediate renders

2. State Management
   - Agent states
   - Processing progress
   - Analytics data

## Security Considerations
1. API Key Management
   - Secure storage in .env
   - Key rotation support
   - Access level control

2. Content Protection
   - Secure video storage
   - Access logging
   - Rate limiting

## Scalability
1. Horizontal Scaling
   - Multiple agent instances
   - Load balancing
   - Queue-based processing

2. Resource Management
   - Disk space monitoring
   - Memory usage optimization
   - CPU load balancing

## Future Enhancements
1. Real-time Processing
   - Stream processing support
   - Live content monitoring
   - Instant viral detection

2. Advanced AI Features
   - Custom model training
   - Improved moment detection
   - Automated A/B testing

3. Platform Expansion
   - Additional social media platforms
   - Custom content optimization
   - Cross-platform analytics 