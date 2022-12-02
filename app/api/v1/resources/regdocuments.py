"""
DRS Registration document resource package.
Copyright (c) 2018-2020 Qualcomm Technologies, Inc.
All rights reserved.
Redistribution and use in source and binary forms, with or without modification, are permitted (subject to the limitations in the disclaimer below) provided that the following conditions are met:

    Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
    Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
    Neither the name of Qualcomm Technologies, Inc. nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
    The origin of this software must not be misrepresented; you must not claim that you wrote the original software. If you use this software in a product, an acknowledgment is required by displaying the trademark/log as per the details provided here: https://www.qualcomm.com/documents/dirbs-logo-and-brand-guidelines
    Altered source versions must be plainly marked as such, and must not be misrepresented as being the original software.
    This notice may not be removed or altered from any source distribution.

NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY THIS LICENSE. THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import json
from datetime import datetime

from flask import Response, request
from flask_restful import Resource
from flask_babel import lazy_gettext as _
from marshmallow import ValidationError

from app import app, db
from app.api.v1.helpers.error_handlers import REG_NOT_FOUND_MSG
from app.api.v1.helpers.response import MIME_TYPES, CODES
from app.api.v1.helpers.utilities import Utilities
from app.api.v1.models.regdetails import RegDetails
from app.api.v1.models.regdocuments import RegDocuments
from app.api.v1.models.status import Status
from app.api.v1.schema.regdocuments import RegistrationDocumentsSchema
from app.api.v1.schema.regdocumentsupdate import RegistrationDocumentsUpdateSchema
from app.api.v1.models.notification import Notification
from app.api.v1.models.eslog import EsLog


class RegDocumentRoutes(Resource):
    """Class for handling Registration Document Routes."""

    @staticmethod
    def get(reg_id):
        """GET method handler, returns request documents."""
        if not reg_id.isdigit() or not RegDetails.exists(reg_id):
            return Response(app.json_encoder.encode(REG_NOT_FOUND_MSG), status=CODES.get("UNPROCESSABLE_ENTITY"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        try:
            schema = RegistrationDocumentsSchema()
            documents = RegDocuments.get_by_reg_id(reg_id)
            documents = schema.dump(documents, many=True).data
            '''if doc_id:
                if not doc_id.isdigit():
                    documents = DOC_NOT_FOUND_MSG
                else:
                    documents = list(filter(lambda doc: int(doc['id']) == int(doc_id), documents))
                    documents = documents[0] if documents else DOC_NOT_FOUND_MSG
            '''
            return Response(json.dumps(documents), status=CODES.get("OK"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))

        except Exception as e:  # pragma: no cover
            app.logger.exception(e)
            data = {
                "message": [_("Error retrieving results. Please try later.")]
            }

            return Response(app.json_encoder.encode(data), status=CODES.get("BAD_REQUEST"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        finally:
            db.session.close()

    @staticmethod
    def post():
        """POST method handler, creates registration documents."""
        reg_id = request.form.to_dict().get('reg_id', None)
        if not reg_id or not reg_id.isdigit() or not RegDetails.exists(reg_id):
            return Response(app.json_encoder.encode(REG_NOT_FOUND_MSG), status=CODES.get("UNPROCESSABLE_ENTITY"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))

        try:
            schema = RegistrationDocumentsSchema()
            time = datetime.now().strftime('%Y%m%d%H%M%S')
            args = request.form.to_dict()
            args = Utilities.update_args_with_file(request.files, args)
            reg_details = RegDetails.get_by_id(reg_id)
            if reg_details:
                args.update({'reg_details_id': reg_details.id, 'status': reg_details.status})
            else:
                args.update({'reg_details_id': ''})

            validation_errors = schema.validate(args)
            if validation_errors:
                return Response(app.json_encoder.encode(validation_errors), status=CODES.get("UNPROCESSABLE_ENTITY"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))

            tracking_id = reg_details.tracking_id
            created = RegDocuments.bulk_create(request.files, reg_details, time)
            response = Utilities.store_files(request.files, tracking_id, time)
            if response:
                return Response(json.dumps(response), status=CODES.get("UNPROCESSABLE_ENTITY"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))
            reg_details.update_status('Pending Review')
            message = schema.dump(created, many=True).data

            log = EsLog.new_doc_serialize(message, request_type="Document Registration", regdetails=reg_details,
                                          reg_status="Pending Review", method='Post', request='Registration')
            db.session.commit()
            EsLog.insert_log(log)
            return Response(json.dumps(message), status=CODES.get("OK"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        except Exception as e:  # pragma: no cover
            db.session.rollback()
            app.logger.exception(e)

            data = {
                'message': _('request document addition failed, check for valid formats.')
            }

            return Response(app.json_encoder.encode(data), status=CODES.get('INTERNAL_SERVER_ERROR'),
                            mimetype=MIME_TYPES.get('APPLICATION_JSON'))
        except es.ElasticsearchException as e:
            db.session.rollback()
            app.logger.exception(e)
            data = {
                'message': _('request document addition failed')
            }

            return Response(app.json_encoder.encode(data), status=CODES.get('INTERNAL_SERVER_ERROR'),
                            mimetype=MIME_TYPES.get('APPLICATION_JSON'))
        finally:
            db.session.close()

    @staticmethod
    def put():
        """PUT method handler, updates documents."""
        reg_id = request.form.to_dict().get('reg_id', None)
        if not reg_id or not reg_id.isdigit() or not RegDetails.exists(reg_id):
            return Response(app.json_encoder.encode(REG_NOT_FOUND_MSG), status=CODES.get("UNPROCESSABLE_ENTITY"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))

        try:
            schema = RegistrationDocumentsUpdateSchema()
            time = datetime.now().strftime('%Y%m%d%H%M%S')
            args = request.form.to_dict()
            args = Utilities.update_args_with_file(request.files, args)
            reg_details = RegDetails.get_by_id(reg_id)
            if reg_details:
                args.update({'reg_details_id': reg_details.id, 'status': reg_details.status})
            else:
                args.update({'reg_details_id': ''})
            validation_errors = schema.validate(args)
            if validation_errors:
                return Response(app.json_encoder.encode(validation_errors), status=CODES.get("UNPROCESSABLE_ENTITY"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))

            tracking_id = reg_details.tracking_id
            updated = RegDocuments.bulk_update(request.files, reg_details, time)
            response = Utilities.store_files(request.files, tracking_id, time)
            if response:
                return Response(json.dumps(response), status=CODES.get("UNPROCESSABLE_ENTITY"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))
            if reg_details.status == Status.get_status_id('Information Requested'):
                reg_details.update_status('In Review')
                message = 'The request {id} has been updated.'.format(id=reg_details.id)
                notification = Notification(reg_details.reviewer_id, reg_details.id,
                                            'registration_request', reg_details.status, message)
                notification.add()
            else:
                reg_details.update_status('Pending Review')
            response = schema.dump(updated, many=True).data
            message = schema.dump(updated, many=True).data

            log = EsLog.new_doc_serialize(message, request_type="Update Registration Documents", regdetails=reg_details,
                                          reg_status="Pending Review", method='Put', request='Registration')

            db.session.commit()
            EsLog.insert_log(log)

            return Response(json.dumps(response), status=CODES.get("OK"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        except Exception as e:  # pragma: no cover
            db.session.rollback()
            app.logger.exception(e)

            data = {
                'message': _('request document updation failed, please try again later.')
            }

            return Response(app.json_encoder.encode(data), status=CODES.get('INTERNAL_SERVER_ERROR'),
                            mimetype=MIME_TYPES.get('APPLICATION_JSON'))
        finally:
            db.session.close()
