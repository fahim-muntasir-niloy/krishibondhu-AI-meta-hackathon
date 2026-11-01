"""Agent tools. Real: get_weather (Open-Meteo), geocode_location (OpenStreetMap),
search_internet (Muse web search), segment_image (SAM 3.1), make_picture_card (Muse Image),
search_images (Wikimedia Commons), the DAE pesticide register (find_registered_pesticides, lookup_pesticide_product),
the crop-case tracker
(start_crop_case, start_cultivation_plan, update/get_crop_case), officer booking (find_officer_slots,
book_officer_session, change_officer_booking) and long-term memory
(create_or_update_user_memory, fetch_user_memory), and the Krishoker Janala
advice (search_crop_problems, get_crop_problem)."""

from meta_hackathon.tools.booking import book_officer_session, change_officer_booking, find_officer_slots
from meta_hackathon.tools.cases import get_crop_case, start_crop_case, start_cultivation_plan, update_crop_case
from meta_hackathon.tools.geocode import geocode_location
from meta_hackathon.tools.image_search import search_images
from meta_hackathon.tools.knowledge import get_crop_problem, search_crop_problems
from meta_hackathon.tools.memory import create_or_update_user_memory, fetch_user_memory
from meta_hackathon.tools.pesticides import find_registered_pesticides, lookup_pesticide_product
from meta_hackathon.tools.picture_card import make_picture_card
from meta_hackathon.tools.segment import segment_image
from meta_hackathon.tools.weather import get_weather
from meta_hackathon.tools.web_search import search_internet

ALL_TOOLS = [
    search_internet,
    get_weather,
    search_crop_problems,
    get_crop_problem,
    find_registered_pesticides,
    lookup_pesticide_product,
    find_officer_slots,
    book_officer_session,
    change_officer_booking,
    geocode_location,
    segment_image,
    search_images,
    make_picture_card,
    start_crop_case,
    start_cultivation_plan,
    update_crop_case,
    get_crop_case,
    create_or_update_user_memory,
    fetch_user_memory,
]

__all__ = ["ALL_TOOLS"]
