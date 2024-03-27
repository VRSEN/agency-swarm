from agency_swarm import Agency
from ItineraryPlannerAgent import ItineraryPlannerAgent
from DestinationSelectorAgent import DestinationSelectorAgent
from CEOAgent import CEOAgent

ceoAgent = CEOAgent()
destinationSelectorAgent = DestinationSelectorAgent()
itineraryPlannerAgent = ItineraryPlannerAgent()

agency = Agency([ceoAgent, [ceoAgent, destinationSelectorAgent],
                 [ceoAgent, itineraryPlannerAgent]],
                shared_instructions='./agency_manifesto.md')

if __name__ == '__main__':
    agency.demo_gradio()