"""
the main entry point for all urls
"""
from tiddlyweb.filters import parse_for_filters
from tiddlyweb.control import get_tiddlers_from_bag
from tiddlyweb.model.bag import Bag
from tiddlyweb.web.handler.recipe import get_tiddlers as recipe_tiddlers
from tiddlyweb.web.handler.bag import get_tiddlers as bag_tiddlers
from tiddlyweb.web.handler.tiddler import get as tiddler_get

import re


class NoTiddlyURLFoundError(IOError):
    """
    This shouldn't ever be raised in practise, as if we get 
    into this module, the url has already matched so should 
    match again. If you get this, there is a bug in the code 
    somewhere
    """
    pass

class InvalidDestinationURL(IOError):
    """
    This is raised when the URL given cannot be figured out.
    This is due to invalid syntax when inputting the url to
    map to.
    """
    pass

def get_handler(environ, start_response):
    """
    selector comes to this function when a tiddlyUrl is found. 
    
    retrieve the recipe/serialization details and pass to 
    tiddlyweb.web.handler.recipe.get_tiddlers
    """
    selector_variables = extract_variables(environ['wsgiorg.routing_args'][1])
    
    potential_urls = get_urls(environ['tiddlyweb.config']['url_bag'], environ['tiddlyweb.store'])
    destination_url = match_url(environ['tiddlyweb.config']['selector'], environ['selector.matches'][0], potential_urls)[1]
    
    destination_url = replace_url_patterns(selector_variables, destination_url)
    
    if is_redirect(destination_url):
        if destination_url.startswith('www.'):
            destination_url = 'http://' + destination_url
        #redirect to the url and return
        start_response('301 Moved Permanently', [
            ('Location', destination_url)
            ])
        return_link = '''<html>
<head>
<title>TiddlyURL Redirect</title>
</head>
<body>
Please see <a href="%s">%s</a>
</body>
</html>''' % (destination_url, destination_url)
        return return_link
    
    try:
        url_part, custom_filters = destination_url.split('?', 1)
    except ValueError:
        url_part = destination_url
        custom_filters = None
    
    mime_type = 'default'
    destination_parts = figure_destination(url_part)
    for part, value in destination_parts.iteritems():
        if part == 'extension':
            environ['tiddlyweb.extension'] = str(value)
            mime_type = environ['tiddlyweb.config']['extension_types'].get(value, None)
        else:
            environ['wsgiorg.routing_args'][1][part] = str(value)
    
    destination_parts.update(selector_variables)
    environ['tiddlyweb.recipe_template'] = destination_parts
            
    filters = figure_filters(environ['tiddlyweb.filters'], custom_filters)
    environ['tiddlyweb.filters'] = filters
    
    #set tiddlyweb.type to make sure we call the correct serializer
    environ['tiddlyweb.type'] = [mime_type]
    
    if 'tiddler_name' in environ['wsgiorg.routing_args'][1]:
        return tiddler_get(environ, start_response)
    elif 'recipe_name' in environ['wsgiorg.routing_args'][1]:
        return recipe_tiddlers(environ, start_response)
    elif 'bag_name' in environ['wsgiorg.routing_args'][1]:
        return bag_tiddlers(environ, start_response)
    
    raise InvalidDestinationURL('URL \'%s\' is incorrectly formatted' % destination_url)

def match_url(selector, url, potential_urls):
    """
    match the current url with the correct url in the url_bag
    
    return a tuple of (selector_path, destination_url)
    """
    for selector_path, destination_url in potential_urls:
        #turn selector_path into the same regex that will appear in selector.matches
        url_regex = selector.parser.__call__(selector_path)
        if re.search(url_regex, url):
            #we have found our url
            return (selector_path, destination_url)
    raise NoTiddlyURL('URL not found in selector')

def get_urls(url_bag, store):
    """
    retrieve a list of selector/destination pairs based
    on the tiddlers in the url bag
    """
    bag = Bag(url_bag)
    bag = store.get(bag)
    tiddlers = get_tiddlers_from_bag(bag)
    return ((tiddler.title, tiddler.text) for tiddler in tiddlers)

def is_redirect(destination_url):
    """
    determine whether the url is a redirect, or a mask
    for another tiddlyweb url
    
    return True/False
    """
    regex = '^(?:\w+:\/\/\/*)|www\.'
    if re.search(regex, destination_url):
        return True
    return False

def figure_filters(filters, custom_filters):
    """
    figure out the filters that have been added to the query
    string and match them with filters in the destination. 
    
    Override any that match.
    
    return a list of filter functions
    """
    if custom_filters:
        custom_filters = parse_for_filters(custom_filters)[0]
        #strip duplicate filters
        result_filters = [custom_filter for custom_filter in custom_filters if custom_filter[1][0] not in [user_filter[1][0] for user_filter in filters]]
        if len(filters) > 0:
            result_filters.extend(filters)
        return result_filters
    return filters

def figure_destination(url_part):
    """
    Figure out where we are going.
    
    return bag/recipe/tiddler name and extension
    """
    regex = '^\/((?:recipes)|(?:bags))\/(\w+)\/tiddlers(?:\/(\w+))?(?:\.(\w+))?(?:\??.*)'
    result = {}
    
    matches = re.findall(regex, url_part)
    for match in matches:
        container_type, container_name, tiddler, extension = match
        if container_type in ['recipes', 'bags']:
            result['%s_name' % container_type[:-1]] = container_name
        if tiddler:
            result['tiddler_name'] = tiddler
        if extension:
            result['extension'] = extension
            
    if not result:
        raise InvalidDestinationURL('URL \'%s\' is incorrectly formatted' % url_part)
    
    return result
    

def extract_variables(routing_args):
    """
    extract wsgiorg.routing_args and set as appropriate
    figure out the standard tiddlyweb url that we are masking
    and extract all the necessary variables
    
    returns a dict of all variables found
    """
    variables = {}
    
    if routing_args:
        for element, value in routing_args.iteritems():
            variables[element] = value
            
    return variables

def replace_url_patterns(replace_variables, url):
    """
    replace any variables specified in the desired url, with any
    patterns specified in selector.
    
    uses recipe like syntax (ie - /recipes/{{ foo }}/tiddlers)
    
    returns the new url
    """
    for index, value in replace_variables.iteritems():
        if value is not None:
            url = url.replace('{{ %s }}' % index, value)
    
    return url