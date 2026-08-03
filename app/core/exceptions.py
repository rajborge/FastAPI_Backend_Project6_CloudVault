class AppException(Exception):
    pass


class EmailAlreadyExistsException(AppException):
    pass


class UsernameAlreadyExistsException(AppException):
    pass


class InvalidCredentialsException(AppException):
    pass


class UserNotFoundException(AppException):
    pass


class InactiveUserException(AppException):
    pass

class FolderAlreadyExists(AppException):
    pass

class FolderNotFound(AppException):
    pass

class StorageQuotaExceededException(AppException):
    pass

class ShareNotFound(AppException):
    pass

class ShareLinkExpired(AppException):
    pass

class InvalidShareException(AppException):
    pass

class DuplicateFileNameException(AppException):
    pass