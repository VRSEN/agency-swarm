from agency_swarm import Agency
from AccommodationsAndActivitiesAgent import AccommodationsAndActivitiesAgent
from ItineraryPlannerAgent import ItineraryPlannerAgent
from CEOAgent import CEOAgent


agency = Agency([ceo, itineraryPlannerAgent, accommodationsActivitiesAgent, budgetPlannerAgent, localExpertAgent, [ceo, itineraryPlannerAgent],
 [itineraryPlannerAgent, accommodationsActivitiesAgent],
 [itineraryPlannerAgent, budgetPlannerAgent],
 [itineraryPlannerAgent, localExpertAgent],
 [accommodationsActivitiesAgent, user],
 [budgetPlannerAgent, user],
 [localExpertAgent, user]],
shared_instructions='./agency_manifesto.md')

if __name__ == '__main__':
    agency.demo_gradio()
