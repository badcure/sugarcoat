import pprint
import sugarcoat.base
import sugarcoat.api.base
import sugarcoat.rackspace_api.identity
import sugarcoat.rackspace_api.base
import re
import flask
import flask.ext.login


@sugarcoat.api.base.app.template_filter('print_headers')
def print_headers(obj):
    result = ''
    for key, value in obj.items():
        result += '{0}: {1}\n'.format(key, value)
    return result


@sugarcoat.api.base.app.template_filter('convert_to_urls')
def convert_to_urls(result):
    if not isinstance(result, str):
        result = str(pprint.pformat(result))
    if not flask.g.user_info:
        return result
    if isinstance(flask.g.list_obj, sugarcoat.base.APIBase):
        for replace_url, replace_url_info in flask.g.list_obj.get_identity().url_to_catalog_dict():
            result = result.replace('/' + '/'.join(replace_url_info), replace_url)

    for url, replace_url_info in flask.g.user_info.url_to_catalog_dict():
        match_url = re.compile("'({0})/*([^']*)'".format(url))
        if len(replace_url_info) == 3:
            result = match_url.sub(r"<a href='/{0}/{1}/{2}/\2'>\1/\2</a>".format(*replace_url_info), result)
        else:
            result = match_url.sub(r"<a href='/{0}/{1}/\2'>\1/\2</a>".format(*replace_url_info), result)

    return result


# noinspection PyUnusedLocal
@sugarcoat.api.base.app.before_request
def before_request(*args, **kwargs):
    flask.g.user_info = sugarcoat.rackspace_api.identity.Identity()
    if 'user_info' in flask.session:
        flask.g.user_info = sugarcoat.rackspace_api.identity.Identity(auth_info=flask.session['user_info'])

    flask.g.api_response = None
    flask.g.list_obj = None


@sugarcoat.api.base.app.after_request
def after_request(response):
    return response


def display_json(response, region, template_kwargs=None,  **kwargs):
    if not template_kwargs:
        template_kwargs = dict()

    try:
        if isinstance(response, sugarcoat.rackspace_api.base.RackAPIResult):
            for mime_type, priority in flask.request.accept_mimetypes:
                if mime_type == 'text/html':
                    return flask.Response(flask.render_template(
                        'json_template.html', json_result=response, additional_urls=convert_to_related(
                            region=region, api_result=response, **kwargs), **template_kwargs))
                elif mime_type == 'application/json' or mime_type == '*/*':
                    return flask.jsonify(response, **kwargs)
    except IndexError:
        pass

    return flask.jsonify(response, **kwargs)


# noinspection PyUnusedLocal
def convert_to_related(region, api_result, **kwargs):
    resource_kwargs = api_result.get_resources()
    if 'region' not in resource_kwargs:
        resource_kwargs['region'] = region
    result = {'links': flask.g.list_obj.filled_out_urls(tenant_id=flask.g.user_info.tenant_id, **resource_kwargs)}
    if isinstance(flask.g.list_obj, sugarcoat.base.APIBase):
        url_list_to_replace = flask.g.list_obj.get_identity().url_to_catalog_dict()
    else:
        return

    for index, url in enumerate(result['links']['populated']):
        for replace_url, replace_url_info in url_list_to_replace:
            url = url.replace('/' + '/'.join(replace_url_info), replace_url)
            new_regex = "^({0})/*([^']*)".format(replace_url)
            match_url = re.compile(new_regex)

            if replace_url in url and '_UNDEFINED' not in url:

                if len(replace_url_info) == 3:
                    result['links']['populated'][index] = match_url.sub(
                        r"<a href='/{0}/{1}/{2}/\2'>\1/\2</a>".format(*replace_url_info), url)
                else:
                    result['links']['populated'][index] = match_url.sub(
                        r"<a href='/{0}/{1}/\2'>\1/\2</a>".format(*replace_url_info), url)
            elif replace_url in url:
                result['links']['populated'][index] = match_url.sub(r"\1/\2", url)

    return result
