from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from typing import Iterable, Optional, Set

# Set a reasonable precision for monetary operations
getcontext().prec = 28

_CENT = Decimal('0.01')
_QTY = Decimal('0.00000001')


class OperationValidationError(Exception):
    """Base class for operation validation errors."""


class InvalidAmountError(OperationValidationError):
    """Raised when an amount is invalid (non-numeric, zero, or negative)."""


class UnsupportedSymbolError(OperationValidationError, KeyError):
    """Raised when an instrument symbol is not supported."""


class InsufficientFundsError(OperationValidationError):
    """Raised when a requested monetary operation would overdraw available funds."""


class InsufficientHoldingsError(OperationValidationError):
    """Raised when attempting to operate on more quantity than is held."""


def _to_decimal_cents(value) -> Decimal:
    """Convert value to Decimal and quantize to cents.

    Accepts Decimal, int, float, or str. Raises InvalidAmountError for
    unconvertible values.
    """
    try:
        dec = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidAmountError(f"Invalid monetary amount: {value!r}") from exc
    return dec.quantize(_CENT, rounding=ROUND_HALF_UP)


def _to_quantity(value) -> Decimal:
    """Convert value to Decimal and quantize to 8 decimal places for quantities.

    Raises InvalidAmountError for unconvertible values.
    """
    try:
        dec = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidAmountError(f"Invalid quantity value: {value!r}") from exc
    return dec.quantize(_QTY, rounding=ROUND_HALF_UP)


class OperationValidator:
    """Validator for common financial operations.

    Responsibilities:
      - Validate monetary amounts (convertible, positive, quantized to cents).
      - Validate instrument symbols against an optional supported set.
      - Validate sufficient funds for a monetary operation.
      - Validate sufficient holdings/quantity for trade operations.

    This class is intentionally lightweight and has no external dependencies
    beyond the Python standard library.
    """

    def __init__(self, supported_symbols: Optional[Iterable[str]] = None) -> None:
        """Create a validator.

        supported_symbols: optional iterable of symbol strings (case-insensitive).
        If provided the validator will treat other symbols as unsupported.
        """
        if supported_symbols is None:
            self._supported: Optional[Set[str]] = None
        else:
            # store uppercase normalized symbols
            self._supported = {str(s).upper() for s in supported_symbols if s is not None}

    def set_supported_symbols(self, symbols: Iterable[str]) -> None:
        """Replace the supported symbols set."""
        self._supported = {str(s).upper() for s in symbols if s is not None}

    def supported_symbols(self) -> Optional[Set[str]]:
        """Return a copy of the supported symbols set or None if unrestricted."""
        if self._supported is None:
            return None
        return set(self._supported)

    def is_supported(self, symbol: Optional[str]) -> bool:
        """Return True if symbol is supported (case-insensitive).

        If no supported set was provided at construction time, all non-empty
        string symbols are considered supported.
        """
        if not isinstance(symbol, str) or not symbol:
            return False
        if self._supported is None:
            return True
        return symbol.upper() in self._supported

    def validate_symbol(self, symbol: Optional[str]) -> str:
        """Validate symbol is a non-empty string and supported.

        Returns the normalized (uppercased) symbol on success. Raises
        UnsupportedSymbolError for invalid/unsupported symbols.
        """
        if not isinstance(symbol, str) or not symbol:
            raise UnsupportedSymbolError(f"invalid symbol: {symbol!r}")
        up = symbol.upper()
        if self._supported is not None and up not in self._supported:
            raise UnsupportedSymbolError(f"symbol not supported: {symbol!r}")
        return up

    def validate_amount(self, amount) -> Decimal:
        """Validate and normalize a monetary amount.

        Converts the input to a Decimal quantized to cents and ensures it is
        strictly positive. Returns the quantized Decimal. Raises
        InvalidAmountError on failure.
        """
        dec = _to_decimal_cents(amount)
        if dec <= Decimal('0'):
            raise InvalidAmountError(f"amount must be positive: {amount!r}")
        return dec

    def validate_non_negative_amount(self, amount) -> Decimal:
        """Like validate_amount but allows zero (non-negative check).

        Returns a Decimal quantized to cents or raises InvalidAmountError.
        """
        dec = _to_decimal_cents(amount)
        if dec < Decimal('0'):
            raise InvalidAmountError(f"amount must be non-negative: {amount!r}")
        return dec

    def validate_sufficient_funds(self, balance, amount) -> Decimal:
        """Ensure balance is sufficient for amount.

        Both balance and amount may be Decimal/int/str/float. The amount is
        validated to be positive. Returns the normalized amount Decimal on
        success. Raises InsufficientFundsError if amount > balance.
        """
        amt = self.validate_amount(amount)
        try:
            bal = _to_decimal_cents(balance)
        except InvalidAmountError:
            # If balance is not convertible treat as insufficient
            raise InsufficientFundsError(f"invalid balance: {balance!r}")
        if amt > bal:
            raise InsufficientFundsError(f"insufficient funds: required {amt}, available {bal}")
        return amt

    def validate_sufficient_quantity(self, holding_quantity, quantity) -> Decimal:
        """Ensure holding_quantity is sufficient for the requested quantity.

        Both holding_quantity and quantity may be Decimal/int/str/float. The
        requested quantity must be positive. Returns the normalized quantity
        Decimal on success. Raises InsufficientHoldingsError if insufficient.
        """
        qty = _to_quantity(quantity)
        if qty <= Decimal('0'):
            raise InvalidAmountError(f"quantity must be positive: {quantity!r}")
        try:
            hold = _to_quantity(holding_quantity)
        except InvalidAmountError:
            raise InsufficientHoldingsError(f"invalid holding quantity: {holding_quantity!r}")
        if qty > hold:
            raise InsufficientHoldingsError(f"insufficient holdings: requested {qty}, available {hold}")
        return qty


__all__ = [
    'OperationValidator',
    'OperationValidationError',
    'InvalidAmountError',
    'UnsupportedSymbolError',
    'InsufficientFundsError',
    'InsufficientHoldingsError',
]


# For demonstration: print the module source when run directly
if __name__ == '__main__':
    import inspect
    print(inspect.getsource(OperationValidator))