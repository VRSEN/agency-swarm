from agency_swarm.agents.content_acquisition.content_acquisition_agent import ContentAcquisitionAgent

def main():
    print("Initializing Content Acquisition Agent...")
    agent = ContentAcquisitionAgent()
    
    # Test video URL (short video for testing)
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    print(f"\nTesting video download from {test_url}")
    try:
        result = agent.download_video(test_url)
        print("\nDownload successful!")
        print(f"Video saved to: {result['video_path']}")
        print(f"Subtitles: {result['subtitle_paths']}")
        print(f"Video info: {result['video_info']}")
        
        print("\nListing all downloads:")
        downloads = agent.list_downloads()
        for download in downloads:
            print(f"- {download['video_path']} ({download['size_mb']} MB)")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main() 