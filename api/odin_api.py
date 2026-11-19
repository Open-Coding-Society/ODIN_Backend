from flask import Blueprint
from flask_restful import Api, Resource # used for REST API building
from model.odin_site import OdinSite

odin_api = Blueprint('odin_api', __name__,
                   url_prefix='/api/odin')

# API docs https://flask-restful.readthedocs.io/en/latest/api.html
api = Api(odin_api)

class OdinAPI:
    """
    What the ODIN Diagnostics website shows, read by its frontend. These routes are public on
    purpose: a visitor has no account, and everything here is shown on the public site.
    """

    class _Site(Resource):  # The basics every page shows
        def get(self): # Read method
            ''' The company name, tagline and contact details '''
            site = OdinSite.current()
            if site is None:
                return {'message': 'The ODIN site content has not been set up.'}, 404
            return site.read()

    # building RESTapi endpoint
    api.add_resource(_Site, '/site')
