import warnings

from fireo import fields
from fireo.managers.managers import Manager
from fireo.models.errors import AbstractNotInstantiate, ModelSerializingWrappedError
from fireo.models.model_meta import ModelMeta
from fireo.queries.errors import InvalidKey
from fireo.utils import utils


class Model(metaclass=ModelMeta):
    """Provide easy way to handle firestore features

    Model is used to handle firestore operation easily and provide additional features for best
    user experience.

    Example
    -------
    .. code-block:: python

        class User(Model):
            username = TextField(required=True)
            full_name = TextField()
            age = NumberField()

        user = User()
        user.username = "Axeem"
        user.full_name = "Azeem Haider"
        user.age = 25
        user.save()

        # or you can also pass args into constructor
        user = User(username="Axeem", full_name="Azeem", age=25)
        user.save()

        # or you can use it via managers
        user = User.collection.create(username="Axeem", full_name="Azeem", age=25)

    Attributes
    ----------
    _meta : Meta
        Hold all model information like model fields, id, manager etc

    id : str
        Model id if user specify any otherwise it will create automatically from firestore
        and attached with this model

    key : str
        Model key which contain the model collection name and model id and parent if provided, Id can be user defined
        or generated from firestore

    _update_doc: str
        Update doc hold the key which is used to update the document

    parent: str
        Parent key if user specify

    collection_name : str
        Model name which is saved in firestore if user not specify any then Model class will convert
        automatically in collection name

        For example: UserProfile will be user_profile

    collection : Manager
        Class level attribute through this you can access manager which can be used to save, retrieve or
        update the model in firestore

        Example:
        -------
        .. code-block:: python
            class User(Model):
                name = TextField()

            user = User.collection.create(name="Azeem")

    Methods
    --------
    _get_fields() : dict
        Private method that return values of all attached fields.

    save() : Model instance
        Save the model in firestore collection

    update(doc_key, transaction) : Model instance
        Update the existing document, doc_key optional can be set explicitly

    _set_key(doc_id):
        Set the model key

    Raises
    ------
    AbstractNotInstantiate:
        Abstract model can not instantiate
    """
    # Id of the model specify by user or auto generated by firestore
    # It can be None if user changed the name of id field it is possible
    # to call it from different name e.g user_id
    id = None

    # Private for internal user but there is key property which hold the
    # current document id and collection name and parent if any
    _key = None

    # For sub collection there must be a parent
    parent = ""

    # Hold all the information about the model fields
    _meta = None

    # This is for manager
    collection: Manager = None

    # Collection name for this model
    collection_name = None

    # Track which fields are changed or not
    # it is useful when updating document
    _field_changed = None

    # Update doc hold the key which is used to update the document
    _update_doc = None

    _create_time = None
    _update_time = None

    def __init__(self, *args, **kwargs):
        assert not args, 'You must use keyword arguments when instantiating a model'
        # check this is not abstract model otherwise stop creating instance of this model
        if self._meta.abstract:
            raise AbstractNotInstantiate(
                f'Can not instantiate abstract model "{self.__class__.__name__}"')

        self._field_changed = []

        # Allow users to set fields values direct from the constructor method
        for k, v in kwargs.items():
            setattr(self, k, v)

        # Create instance for nested model
        # for direct assignment to nested model
        for f in self._meta.field_list.values():
            if isinstance(f, fields.NestedModelField):
                if f.name not in kwargs:
                    setattr(self, f.name, f.nested_model())
                elif isinstance(kwargs[f.name], dict):
                    warnings.warn(
                        'Use Model.from_dict to deserialize from dict',
                        DeprecationWarning
                    )
                    setattr(self, f.name, f.nested_model.from_dict(kwargs[f.name]))

    @classmethod
    def from_dict(cls, model_dict):
        """Instantiate model from dict"""
        if model_dict is None:
            return None

        instance = cls()
        instance.populate_from_doc_dict(model_dict)
        return instance

    def to_dict(self):
        """Convert model into dict"""
        model_dict = self.to_db_dict()
        id = 'id'
        if self._meta.id is not None:
            id, _ = self._meta.id
        model_dict[id] = utils.get_id(self.key)
        model_dict['key'] = self.key
        return model_dict

    def to_db_dict(self, ignore_required=False, ignore_default=False, changed_only=False):
        result = {}
        for field in self._meta.field_list.values():
            field: Field  # type: ignore
            if changed_only and field.name not in self._field_changed:
                continue

            try:
                nested_field_value = getattr(self, field.name)
                value = field.get_value(nested_field_value, ignore_required, ignore_default, changed_only)
            except Exception as error:
                path = (field.name,)
                raise ModelSerializingWrappedError(self, path, error) from error

            if value is not None or not self._meta.ignore_none_field:
                result[field.db_column_name] = value

        return result

    def populate_from_doc_dict(self, doc_dict):
        for k, v in doc_dict.items():
            field = self._meta.get_field_by_column_name(k)
            # if missing field setting is set to "ignore" then
            # get_field_by_column_name return None So, just skip this field
            if field is None:
                continue

            val = field.field_value(v, self)
            self._set_orig_attr(field.name, val)

    # Get all the fields values from meta
    # which are attached with this mode
    # to create or update the document
    # return dict {name: value}
    def _get_fields(self, changed_only=False):
        """Get Model fields and values

        Retrieve all fields which are attached with Model from `_meta`
        then get corresponding value from model

        Example
        -------
        .. code-block:: python

            class User(Model):
                name = TextField()
                age = NumberField()

            user = User()
            user.name = "Azeem"
            user.age = 25

            # if you call this method `_get_field()` it will return dict{name, val}
            # in this case it will be
            {name: "Azeem", age: 25}

        Returns
        -------
        dict:
            name value dict of model
        """
        field_list = {}
        for f in self._meta.field_list.values():
            v = getattr(self, f.name)
            if (
                not changed_only or
                f.name in self._field_changed or
                # Currently, there is no way to tell if a MapField has been changed
                isinstance(f, fields.MapField) and v is not None
            ):
                field_list[f.name] = v
        return field_list

    @property
    def _id(self):
        """Get Model id

        User can specify model id otherwise it will return None and generate later from
        firestore and attached to model

        Example
        --------
        .. code-block:: python
            class User(Mode):
                user_id = IDField()

            u = User()
            u.user_id = "custom_doc_id"

            # If you call this property it will return user defined id in this case
            print(self._id)  # custom_doc_id

        Returns
        -------
        id : str or None
            User defined id or None
        """
        if self._meta.id is None:
            return None
        name, field = self._meta.id
        return field.get_value(getattr(self, name))

    @_id.setter
    def _id(self, doc_id):
        """Set Model id

        Set user defined id to model otherwise auto generate from firestore and attach
        it to with model

        Example:
        --------
            class User(Model):
                user_id = IDField()
                name = TextField()

            u = User()
            u.name = "Azeem"
            u.save()

            # User not specify any id it will auto generate from firestore
            print(u.user_id)  # xJuythTsfLs

        Parameters
        ----------
        doc_id : str
            Id of the model user specified or auto generated from firestore
        """
        id = 'id'
        if self._meta.id is not None:
            id, _ = self._meta.id
        setattr(self, id, doc_id)
        # Doc id can be None when user create Model directly from manager
        # For Example:
        #   User.collection.create(name="Azeem")
        # in this any empty doc id send just for setup things
        if doc_id:
            self._set_key(doc_id)

    @property
    def key(self):
        if self._key:
            return self._key
        try:
            k = '/'.join([self.parent, self.collection_name, self._id])
        except TypeError:
            k = '/'.join([self.parent, self.collection_name, '@temp_doc_id'])
        if k[0] == '/':
            return k[1:]
        else:
            return k

    def _set_key(self, doc_id):
        """Set key for model"""
        p = '/'.join([self.parent, self.collection_name, doc_id])
        if p[0] == '/':
            self._key = p[1:]
        else:
            self._key = p

    def get_firestore_create_time(self):
        """returns create time of document in Firestore

        Returns:
            :class:`google.api_core.datetime_helpers.DatetimeWithNanoseconds`,
            :class:`datetime.datetime` or ``NoneType``:
        """
        return self._create_time

    def get_firestore_update_time(self):
        """returns update time of document in Firestore

        Returns:
            :class:`google.api_core.datetime_helpers.DatetimeWithNanoseconds`,
            :class:`datetime.datetime` or ``NoneType``:
        """
        return self._update_time

    def list_subcollections(self):
        """return a list of any subcollections of the doc"""
        if self._meta._referenceDoc is not None:
            return [c.id for c in self._meta._referenceDoc.collections()]

    def save(self, transaction=None, batch=None, merge=None, no_return=False):
        """Save Model in firestore collection

        Model classes can saved in firestore using this method

        Example
        -------
        .. code-block:: python
            class User(Model):
                name = TextField()
                age = NumberField()

            u = User(name="Azeem", age=25)
            u.save()

            # print model id
            print(u.id) #  xJuythTsfLs

        Same thing can be achieved from using managers

        See Also
        --------
        fireo.managers.Manager()

        Returns
        -------
        model instance:
            Modified instance of the model contains id etc
        """
        # pass the model instance if want change in it after save, fetch etc operations
        # otherwise it will return new model instance
        return self.__class__.collection.create(
            self, transaction, batch, merge, no_return, **self._get_fields(changed_only=merge)
        )

    def upsert(self, transaction=None, batch=None):
        """If the document does not exist, it will be created. 
        If the document does exist it should be merged into the existing document.
        """
        return self.save(transaction=transaction, batch=batch, merge=True)

    def update(self, key=None, transaction=None, batch=None):
        """Update the existing document

        Update document without overriding it. You can update selected fields.

        Examples
        --------
        .. code-block:: python
            class User(Model):
                name = TextField()
                age = NumberField()

            u = User.collection.create(name="Azeem", age=25)
            id = u.id

            # update this
            user = User.collection.get(id)
            user.name = "Arfan"
            user.update()

            print(user.name)  # Arfan
            print(user.age)  # 25

        Parameters
        ----------
        key: str
            Key of document which is going to update this is optional you can also set
            the update_doc explicitly

        transaction:
            Firestore transaction

        batch:
            Firestore batch writes
        """

        # Check doc key is given or not
        if key:
            self._update_doc = key

        # make sure update doc in not None
        if self._update_doc is not None and '@temp_doc_id' not in self._update_doc:
            # set parent doc from this updated document key
            self.parent = utils.get_parent_doc(self._update_doc)
            # Get id from key and set it for model
            setattr(self, '_id', utils.get_id(self._update_doc))
            # Add the temp id field if user is not specified any
            if self._id is None and self.id:
                setattr(self._meta, 'id', ('id', fields.IDField()))
        elif self._update_doc is None and '@temp_doc_id' in self.key:
            raise InvalidKey(
                f'Invalid key to update model "{self.__class__.__name__}" ')

        # Get the updated fields
        updated_fields = {}
        for k, v in self._get_fields().items():
            if k in self._field_changed:
                updated_fields[k] = v

        # pass the model instance if want change in it after save, fetch etc operations
        # otherwise it will return new model instance
        return self.__class__.collection._update(self, transaction=transaction, batch=batch, **updated_fields)

    def __setattr__(self, key, value):
        """Keep track which filed values are changed"""
        if key in self._meta.field_list:
            self._field_changed.append(key)
        super(Model, self).__setattr__(key, value)

    def _set_orig_attr(self, key, value):
        """Keep track which filed values are changed"""
        super(Model, self).__setattr__(key, value)
