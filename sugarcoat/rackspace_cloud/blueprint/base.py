import flask
import string
import flask_wtf
import wtforms

import sugarcoat.rackspace_cloud.services
import sugarcoat.api.base
import sugarcoat.rackspace_cloud.base


app = flask.Blueprint('rackspacecloud', __name__, url_prefix='/rackspacecloud')


class LoginFormAPI(flask_wtf.Form):
    username = wtforms.StringField('Username', [wtforms.validators.Length(min=1, max=25)])
    password = wtforms.PasswordField('Rackspace API Key')


class LoginFormPassword(flask_wtf.Form):
    username = wtforms.StringField('Username', [wtforms.validators.Length(min=1, max=25)])
    password = wtforms.PasswordField('Rackspace Password')


class ValidateToken(flask_wtf.Form):
    token = wtforms.PasswordField('Rackspace Authenticated Token')


def display_json(response, region, template_kwargs=None, **kwargs):
    if not template_kwargs:
        template_kwargs = dict()

    try:
        if isinstance(response, sugarcoat.rackspace_cloud.base.RackAPIResult):
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
    flask.g.user_info = sugarcoat.rackspace_cloud.base.Identity()
    if 'user_info' in flask.session:
        flask.g.user_info = sugarcoat.rackspace_cloud.base.Identity(auth_info=flask.session['user_info'])


    flask.g.api_response = None
    flask.g.list_obj = None


@app.after_request
def after_request(response):
    return response


@app.route('/cloudIdentity/all', methods=['GET', 'POST'])
@app.route('/cloudIdentity/all/', methods=['GET', 'POST'])
@app.route('/cloudIdentity/all/<path:new_path>', methods=['GET', 'POST'])
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

    flask.g.list_obj = sugarcoat.rackspace_cloud.services.IdentityAPI(flask.g.user_info)
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

    flask.g.api_response = flask.g.list_obj.get_api_resource(region='all', initial_url_append='/' + new_path, method=method, data=request_data, additional_headers=additional_headers)
    if flask.request.method == 'POST' and form.validate_on_submit():
        flask.g.api_response['request_body'] = flask.g.api_response['request_body'].replace('"'+form.password.data+'"', '"<masked>"')
        if flask.g.api_response['status_code'] == 200:
            flask.session['user_info'] = flask.g.api_response['result']
            flask.g.user_info = sugarcoat.rackspace_cloud.base.Identity(flask.session['user_info'])
    kwargs = flask.g.list_obj.kwargs_from_request(url=new_path, api_result=flask.g.api_response['result'], region='all')

    if 'region' in kwargs:
        del kwargs['region']
    return display_json(response=flask.g.api_response, template_kwargs=template_kwargs, region='all', **kwargs)


@app.route('/<string:servicename>/<string:region>')
@app.route('/<string:servicename>/<string:region>/')
@app.route('/<string:servicename>/<string:region>/<path:new_path>')
def service_catalog_list(servicename,region,new_path=''):
    flask.g.list_obj = sugarcoat.rackspace_cloud.services.get_catalog_api(servicename)(flask.g.user_info)
    query_args = ''
    new_path = ''.join(list(filter(lambda x: x in string.printable, new_path)))

    for key, value in flask.request.args.items():
        query_args += '&{0}={1}'.format(key, value)
    if query_args:
        query_args = '?'+ query_args[1:]
    new_path += query_args
    flask.g.api_response = flask.g.list_obj.get_api_resource(region=region, initial_url_append='/' + new_path)
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
    del flask.session['user_info']
    flask.g.user_info = None
    return flask.redirect('/')


@app.route('/', methods=['GET', 'POST'])
def rackspace_index():
    template_info = dict()

    template_info['form'] = LoginFormAPI(prefix='login')
    template_info['form_validate'] = ValidateToken(prefix='validate')

    if template_info['form'].validate_on_submit():
        # Login and validate the user.
        # user should be an instance of your `User` class
        local_ident = LoginFormAPI(template_info['form'].username.data,
                                                      template_info['form'].password.data)
        if local_ident.token:
            flask.session['user_info'] = local_ident.auth_payload

            flask.flash('Logged in successfully.')

            next_url = flask.request.args.get('next')
            return flask.redirect(next_url or flask.url_for('index'))
        else:
            flask.flash('Invalid login.')
    elif template_info['form'].validate_on_submit():
        # Login and validate the user.
        # user should be an instance of your `User` class
        local_ident = LoginFormPassword(template_info['form_validate'].username.data,
                                                           template_info['form_validate'].password.data)
        if local_ident.token:
            flask.session['user_info'] = local_ident.auth_payload

            flask.flash('Logged in successfully.')

            next_url = flask.request.args.get('next')
            return flask.redirect(next_url or flask.url_for('index'))
        else:
            flask.flash('Invalid login.')


    template_info['message'] = ''
    return flask.Response(flask.render_template('index.html', **template_info))
