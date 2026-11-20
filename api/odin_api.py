from flask import Blueprint, request, send_from_directory
from flask_restful import Api, Resource # used for REST API building
from model.odin_image import IMAGE_FOLDER, image_file, image_type
from model.odin_section import OdinSection, is_name
from model.odin_site import OdinSite

odin_api = Blueprint('odin_api', __name__,
                   url_prefix='/api/odin')

# API docs https://flask-restful.readthedocs.io/en/latest/api.html
api = Api(odin_api)

class OdinAPI:
    """
    The ODIN Diagnostics website's content, for its frontend to read. These routes are public on
    purpose: a visitor has no account, and everything here is shown on the public site.
    """

    class _Site(Resource):  # The basics every page shows
        def get(self): # Read method
            ''' The company name, tagline, contact details, logos and footer lines '''
            site = OdinSite.current()
            if site is None:
                return {'message': 'The ODIN site content has not been set up.'}, 404
            return site.read()

    class _Page(Resource):  # One page's sections
        def get(self): # Read method
            ''' The sections of the page named by ?name=, in the order the page shows them '''
            name = request.args.get('name')
            if not name:
                return {'message': 'Give the page name, as in ?name=home', 'errors': {'name': 'is required'}}, 400
            # Only a well-formed name is looked up. MySQL compares text without regard to case, so
            # Home would find the home page there and not on SQLite.
            sections = OdinSection.for_page(name) if is_name(name) else []
            if not sections:
                return {'message': 'No ODIN page has that name.'}, 404
            return {'page': name, 'sections': [section.read() for section in sections]}

    class _Image(Resource):  # One of the website's images
        def get(self): # Read method
            ''' The image file named by ?name= '''
            name = request.args.get('name')
            if not name:
                return {'message': 'Give the image name, as in ?name=logo-dark.svg'}, 400
            if image_file(name) is None:
                return {'message': 'No ODIN image has that name.'}, 404
            # An hour in the browser's cache: a page shows several images, and without it every view
            # asks for each one again, which also uses up a guest's requests for the minute.
            response = send_from_directory(IMAGE_FOLDER, name, mimetype=image_type(name), max_age=3600)
            # An SVG opened on its own address is a page of this server, and a script in one would run
            # with a signed-in visitor's login. The policy lets it draw (its own styles and the pictures
            # embedded in it) and nothing else, and nosniff keeps each file the type its name says.
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Content-Security-Policy'] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox"
            return response

    # building RESTapi endpoint
    api.add_resource(_Site, '/site')
    api.add_resource(_Page, '/page')
    api.add_resource(_Image, '/image')
