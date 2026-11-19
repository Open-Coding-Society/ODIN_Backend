from flask import Blueprint, request, send_from_directory
from flask_restful import Api, Resource # used for REST API building
from model.odin_image import IMAGE_FOLDER, image_file
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
            ''' The company name, tagline and contact details '''
            site = OdinSite.current()
            if site is None:
                return {'message': 'The ODIN site content has not been set up.'}, 404
            return site.read()

    class _Image(Resource):  # One of the website's images
        def get(self): # Read method
            ''' The image file named by ?name= '''
            name = request.args.get('name')
            if not name:
                return {'message': 'Give the image name, as in ?name=logo-dark.svg'}, 400
            if image_file(name) is None:
                return {'message': 'No ODIN image has that name.'}, 404
            response = send_from_directory(IMAGE_FOLDER, name)
            # An SVG opened on its own could run script as this server. These headers stop that, and
            # stop a browser from treating any image as another kind of file.
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
            return response

    # building RESTapi endpoint
    api.add_resource(_Site, '/site')
    api.add_resource(_Image, '/image')
