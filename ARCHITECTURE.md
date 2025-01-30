# System Architecture

## Overview
Agency Swarm is a multi-agent system designed to automate the creation of viral social media content through AI-powered video processing and enhancement.

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
   - Tools: 
     - TranscriptionTool: Uses OpenAI Whisper for accurate transcription
     - MomentDetectionTool: Identifies viral moments using keyword analysis
     - EmotionAnalysisTool: Analyzes emotional intensity
   - Responsibilities: 
     - Identify high-impact moments using:
       - Emotional intensity detection
       - Keyword density analysis
       - Visual action scoring
   - Implementation:
     - Uses OpenAI Whisper for accurate transcription
     - Implements custom scoring algorithms for moment detection
     - Viral moment detection based on:
       - Keyword presence
       - Emotional intensity
       - Narrative structure
     
4. Creative Agent
   - Tools: 
     - VideoSplitterTool
     - AnimationTool (Stable Diffusion)
     - CaptionTool
     - CompositionTool (FFmpeg)
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

### Storage Structure

```
downloads/
├── videos/         # Original downloaded videos
├── segments/       # Extracted viral moments
├── animations/     # Generated AI frames
├── captioned/      # Frames with captions
└── final/         # Final compositions
```

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

## Testing Strategy
- Unit tests for individual tools
- Integration tests for agent interactions
- End-to-end pipeline testing
- Performance benchmarking

## Monitoring and Analytics
- Processing time tracking
- Resource usage monitoring
- Success/failure rates
- Quality metrics tracking

## Agent Communication Flow
```
[User] -> [Content Acquisition Agent]
           |
           v
      [Analysis Agent]
           |
           v
      [Creative Agent]
           |
           v
[Final Video Output]
```

## Error Handling
- Graceful failure recovery
- Detailed error logging
- Automatic retries for transient failures
- Input validation at each stage
