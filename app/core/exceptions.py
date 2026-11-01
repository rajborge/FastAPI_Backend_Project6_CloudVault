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

class ShareDownloadLimitExceeded(AppException):
    pass

class InvalidShareException(AppException):
    pass

class DuplicateFileNameException(AppException):
    pass

class FileNotFoundException(AppException):
    pass

class FileNotReadyException(AppException):
    pass

class UploadIntentNotFoundException(AppException):
    pass

class UploadIntentExpiredException(AppException):
    pass

class InvalidUploadException(AppException):
    pass

class PermissionNotFoundException(AppException):
    pass

class ObjectStorageConfigurationException(AppException):
    pass

class InvalidFolderMoveException(AppException):
    pass