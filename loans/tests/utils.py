from loans.models import LoanItem, MaterialLoan


def create_loan(material, quantity, **fields):
    """Crea un préstamo por ORM con un renglón (no toca el stock)."""
    loan = MaterialLoan.objects.create(**fields)
    LoanItem.objects.create(loan=loan, material=material, quantity=quantity)
    return loan
