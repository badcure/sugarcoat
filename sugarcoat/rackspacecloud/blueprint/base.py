import flask
import string
import flask_wtf
import wtforms
import re

import sugarcoat.rackspacecloud.services
import sugarcoat.api.base
import sugarcoat.rackspacecloud.base


app = flask.Blueprint('rackspacecloud', __name__, url_prefix='/rackspacecloud', static_folder='static',
                      template_folder='./templates')


class LoginFormAPI(flask_wtf.Form):
    username = wtforms.StringField('Username', [wtforms.validators.Length(min=1, max=25)])
    password = wtforms.PasswordField('Rackspace API Key')


class LoginFormPassword(flask_wtf.Form):
    username = wtforms.StringField('Username', [wtforms.validators.Length(min=1, max=25)])
    password = wtforms.PasswordField('Rackspace Password')


class ValidateToken(flask_wtf.Form):
    tenant_id = wtforms.StringField('Tenant ID', [wtforms.validators.Length(min=1, max=15)])
    token = wtforms.PasswordField('Rackspace Authenticated Token')


def convert_to_related(region, api_result):
    region = region.lower()

    resource_kwargs = api_result.get_resources()
    if 'region' not in resource_kwargs:
        resource_kwargs['region'] = region
    result = {'links': flask.g.list_obj.filled_out_urls(tenant_id=flask.g.user_info.tenant_id, **resource_kwargs)}
    url_list_to_replace = flask.g.list_obj.get_auth().url_to_catalog_dict()
    url_prefix = flask.current_app.blueprints[flask.request.blueprint].url_prefix
    for index, url in enumerate(result['links']['populated']):
        for replace_url, replace_url_info in url_list_to_replace:
            url = url.replace('/' + '/'.join(replace_url_info), replace_url)
            new_regex = "^({0})/*([^']*)".format(replace_url)
            match_url = re.compile(new_regex)

            if replace_url in url and '_UNDEFINED' not in url:

                if len(replace_url_info) == 3:
                    result['links']['populated'][index] = match_url.sub(r"<a href='{url_prefix}/{0}/{1}/{2}/\2'>\1/\2</a>".format(*replace_url_info, url_prefix=url_prefix), url)
                else:
                    result['links']['populated'][index] = match_url.sub(r"<a href='{url_prefix}/{0}/{1}/\2'>\1/\2</a>".format(*replace_url_info, url_prefix=url_prefix), url)
            elif replace_url in url:
                result['links']['populated'][index] = match_url.sub(r"\1/\2", url)

    return result


def display_json(response, region, template_kwargs=None, **kwargs):
    region = region.lower()

    if not template_kwargs:
        template_kwargs = dict()

    try:
        if isinstance(response, sugarcoat.rackspacecloud.base.RackAPIResult):
            for mime_type, priority in flask.request.accept_mimetypes:
                if mime_type == 'text/html':
                    return flask.Response(flask.render_template(
                        'json_template.html', json_result=response, additional_urls=convert_to_related(region=region, api_result=response), **template_kwargs))
                elif mime_type == 'application/json' or mime_type == '*/*':
                    return flask.jsonify(response, **kwargs)
    except IndexError:
        pass

    return flask.jsonify(response, **kwargs)


# noinspection PyUnusedLocal
@app.before_request
def before_request(*args, **kwargs):
    flask.g.user_info = sugarcoat.rackspacecloud.base.Identity()
    if 'user_info' in flask.session:
        flask.g.user_info = sugarcoat.rackspacecloud.base.Identity(auth_info=flask.session['user_info'])


    flask.g.api_response = None
    flask.g.list_obj = None
    flask.g.services = dict()
    for tmp_cls in sugarcoat.rackspacecloud.base.RackAPI.__subclasses__():
        flask.g.services[tmp_cls.catalog_key] = tmp_cls



@app.after_request
def after_request(response):
    return response

@app.route('/cloudIdentity/all', methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/cloudIdentity/all/<path:new_path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def identity_request(new_path=''):
    method = flask.request.method
    request_data = flask.request.data
    additional_headers = {}
    for query_name, query_value in flask.request.args.items():
        if 'sugarcoat_method' in query_name:
            method = query_value
        elif 'sugarcoat_body' in query_name:
            request_data = query_value
        elif 'sugarcoat_header' in query_name:
            new_header = '_'.join(query_name.split('_')[2:])
            additional_headers[new_header] = query_value

    flask.g.list_obj = sugarcoat.rackspacecloud.services.IdentityAPI(flask.g.user_info)
    query_args = ''
    new_path = ''.join(list(filter(lambda x: x in string.printable, new_path)))

    for key, value in flask.request.args.items():
        if 'sugarcoat_' in key:
            continue
        query_args += '&{0}={1}'.format(key, value)
    if query_args:
        query_args = '?'+ query_args[1:]
    new_path += query_args
    template_kwargs = dict()
    template_kwargs['region'] = 'all'
    form = LoginFormAPI(prefix='login')
    form_validate = ValidateToken(prefix='validate')
    if flask.request.method == 'POST' and form.validate_on_submit():
        # Login and validate the user.
        # user should be an instance of your `User` class

        request_data = {
            "auth": {
                "RAX-KSKEY:apiKeyCredentials": {
                    "username": form.username.data,
                    "apiKey": form.password.data
                }
            }
        }
    elif flask.request.method == 'POST' and form_validate.validate_on_submit():
        # Login and validate the user.
        # user should be an instance of your `User` class

        request_data = {'auth': {
            "tenantId": form_validate.tenant_id.data,
            "token": {
                "id": form_validate.token.data
            }}}

    flask.g.api_response = flask.g.list_obj.get_api_resource(
        region='all', initial_url_append='/' + new_path, method=method, data=request_data,
        additional_headers=additional_headers, show_confidential=flask.request.args.get('show_confidential', False))
    if flask.request.method == 'POST' and (form.validate_on_submit() or form_validate.validate_on_submit()):
        if not flask.request.args.get('show_confidential', False):
            flask.g.api_response['request_body'] = flask.g.api_response['request_body'].replace('"'+form.password.data+'"', '"MASKED INFO"')
        if flask.g.api_response['status_code'] == 200:
            flask.session['user_info'] = flask.g.api_response['result']
            flask.g.user_info = sugarcoat.rackspacecloud.base.Identity(flask.session['user_info'])
    kwargs = flask.g.list_obj.kwargs_from_request(url=new_path, api_result=flask.g.api_response['result'], region='all')

    if 'region' in kwargs:
        del kwargs['region']
    return display_json(response=flask.g.api_response, template_kwargs=template_kwargs, region='all', **kwargs)


@app.route('/<string:servicename>/<string:region>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<string:servicename>/<string:region>/', methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<string:servicename>/<string:region>/<path:new_path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def service_catalog_list(servicename,region,new_path=''):
    region = region.lower()
    if not flask.g.user_info.token:
        return flask.redirect(flask.url_for('rackspacecloud.index'))
    flask.g.list_obj = sugarcoat.rackspacecloud.services.get_catalog_api(servicename)(flask.g.user_info)
    query_args = ''
    new_path = ''.join(list(filter(lambda x: x in string.printable, new_path)))

    for key, value in flask.request.args.items():
        query_args += '&{0}={1}'.format(key, value)
    if query_args:
        query_args = '?'+ query_args[1:]
    new_path += query_args
    flask.g.api_response = flask.g.list_obj.get_api_resource(region=region, initial_url_append='/' + new_path,
                                                             show_confidential=flask.request.args.get('show_confidential', False))
    kwargs = flask.g.list_obj.kwargs_from_request(url=new_path, api_result=flask.g.api_response['result'], region=region)

    template_kwargs = dict()
    template_kwargs['region'] = region
    template_kwargs['tenant_id'] = flask.g.user_info.tenant_id

    if 'region' in kwargs:
        del kwargs['region']
    return display_json(response=flask.g.api_response, tenant_id=flask.g.user_info.tenant_id, template_kwargs=template_kwargs, region=region, **kwargs)



@app.route('/auth_token')
def auth_token_view():
    return flask.json.jsonify(flask.g.user_info.display_safe())


@app.route('/login', methods=['GET', 'POST'])
def login_view():
    test =                         {
        "auth": {
            "RAX-KSKEY:apiKeyCredentials": {
                "username": "<input name='login-username'>",
                "apiKey": "<input name='login-password' type='password'>"
            }
        }
    }
    use_token = {'auth': {
        "tenantId": "<input name='validate-tenant_id'>",
        "token": {
            "id": "<input name='validate-token' type='password'>"
        }}}

    template_info = dict()

    template_info['form'] = LoginFormAPI(prefix='login')
    template_info['form_validate'] = ValidateToken(prefix='validate')


    template_info['message'] = ''
    template_info['test_dict'] = test
    template_info['use_token_dict'] = use_token
    if flask.request.method == 'POST' and template_info['form_validate'].validate_on_submit():
        token = template_info['form_validate'].token.data
        flask.g.user_info = sugarcoat.rackspacecloud.base.Identity()
    return flask.Response(flask.render_template('rackspacecloud/login.html', **template_info))


@app.route('/refresh_auth', methods=['GET'])
def refresh_auth_fn():
    # Here we use a class of some kind to represent and validate our
    # client-side form data. For example, WTForms is a library that will
    # handle this for us, and we use a custom LoginFormAPI to validate.
    flask.session['user_info'] = flask.g.user_info.refresh_auth()
    return flask.redirect('/')

@app.route('/logout', methods=['GET'])
def logout_fn():
    # Here we use a class of some kind to represent and validate our
    # client-side form data. For example, WTForms is a library that will
    # handle this for us, and we use a custom LoginFormAPI to validate.
    if 'user_info' in flask.session:
        del flask.session['user_info']
    flask.g.user_info = None
    return flask.redirect('/')


@app.route('/dfw', methods=['GET'], defaults={'region': 'dfw'})
@app.route('/iad', methods=['GET'], defaults={'region': 'iad'})
@app.route('/ord', methods=['GET'], defaults={'region': 'ord'})
@app.route('/syd', methods=['GET'], defaults={'region': 'syd'})
@app.route('/lon', methods=['GET'], defaults={'region': 'lon'})
@app.route('/hkg', methods=['GET'], defaults={'region': 'hkg'})
def region_view(region):
    if not flask.g.user_info.token:
        return flask.redirect(flask.url_for('rackspacecloud.login_view'))

    return flask.Response(flask.render_template('rackspacecloud/region.html', region=region))


@app.route('/', methods=['GET', 'POST'])
def index():
    if not flask.g.user_info.token:
        return flask.redirect(flask.url_for('rackspacecloud.login_view'))
    template_info = dict()


    template_info['message'] = ''

    return flask.Response(flask.render_template('rackspacecloud/index.html', **template_info))
