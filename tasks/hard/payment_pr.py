"""
tasks/hard/payment_pr.py — Hard task: payment processor security audit (3-step).
"""

from __future__ import annotations

from code_review_env.models import GroundTruthIssue
from code_review_env.tasks.base_task import TaskDefinition

# ---------------------------------------------------------------------------
# Unified diff (5 files)
# ---------------------------------------------------------------------------

DIFF = """\
--- a/payments/processor.py
+++ b/payments/processor.py
@@ -25,12 +25,20 @@
 class PaymentProcessor:
     def __init__(self, session: Session, gateway: GatewayClient):
         self.session = session
         self.gateway = gateway
+        self._dup_cache: dict = {}
 
-    def process(self, payment_id: str, amount: float,
-                 metadata: bytes | None = None) -> dict:
+    def process(self, payment_id: str, amount: float,
+                 metadata: bytes | None = None,
+                 extra: bytes | None = None) -> dict:
         \"\"\"Process a payment and record it in the database.\"\"\"
-        if self._is_duplicate(payment_id):
+        if payment_id in self._dup_cache:
             raise ValueError(f"Duplicate payment: {payment_id}")
+        if extra is not None:
+            parsed_extra = pickle.loads(extra)
+            logger.info("Payment extra metadata: %s", parsed_extra)
+        self._dup_cache[payment_id] = True
         charge = self.gateway.charge(amount)
         self._record(payment_id, amount, charge)
         return charge

--- a/payments/serializers.py
+++ b/payments/serializers.py
@@ -14,6 +14,12 @@
 class PaymentSerializer:
     def __init__(self, payment: Payment, include_internal: bool = False):
         self.payment = payment
         self.include_internal = include_internal
 
-    def to_dict(self) -> dict:
+    def to_dict(self, requester_role: str = "user") -> dict:
         data = {
             "id":         self.payment.id,
             "amount":     float(self.payment.amount),
             "status":     self.payment.status,
             "created_at": self.payment.created_at.isoformat(),
         }
+        if self.include_internal:
+            data["customer_ssn_last4"] = self.payment.customer_ssn_last4
+            data["internal_ref"]       = self.payment.internal_ref
         return data

--- a/payments/api.py
+++ b/payments/api.py
@@ -23,8 +23,12 @@
 @router.post("/payments", response_model=PaymentResponse)
 async def create_payment(
     request: PaymentRequest,
     background_tasks: BackgroundTasks,
     db: Session = Depends(get_db),
 ) -> PaymentResponse:
+    is_admin = request.is_admin
+    serializer = PaymentSerializer(payment=None,
+                                   include_internal=is_admin)
     processor = PaymentProcessor(session=db, gateway=gateway_client)
     result = processor.process(
         payment_id=str(uuid4()),
@@ -33,6 +37,9 @@
     )
     background_tasks.add_task(audit_log, result)
-    return PaymentResponse(**result)
+    payment = Payment(**result)
+    return serializer.to_dict()

--- a/payments/models.py
+++ b/payments/models.py
@@ -5,7 +5,7 @@
 class Payment(Base):
     __tablename__ = "payments"
     id              = Column(String, primary_key=True, default=lambda: str(uuid4()))
-    amount          = Column(Numeric(10, 2), nullable=False)
+    amount          = Column(Float, nullable=False)
     status          = Column(String, default="pending")
     created_at      = Column(DateTime, default=datetime.utcnow)
     customer_ssn_last4 = Column(String(4), nullable=True)

--- a/config/logging_config.py
+++ b/config/logging_config.py
@@ -8,7 +8,7 @@
 LOGGING = {
     "version": 1,
     "disable_existing_loggers": False,
-    "handlers": {
-        "file": {"class": "logging.FileHandler", "filename": "/var/log/app.log"}
+    "handlers": {
+        "file": {"class": "logging.FileHandler", "filename": "/tmp/payments.log"}
     },
     "root": {"level": "INFO", "handlers": ["file"]},
 }
"""

# ---------------------------------------------------------------------------
# File contexts — line-number-accurate content
# ---------------------------------------------------------------------------

# payments/processor.py
# Target line numbers:
#   29 = self._dup_cache: dict = {}          (hard_004: unbounded cache)
#   35 = if extra is not None:               (hard_001 start)
#   36 = parsed_extra = pickle.loads(extra)  (hard_001)
#   37 = (closing of pickle block)           (hard_001 end)
#   38 = logger.info(...)                    (hard_002)
#   41 = self._dup_cache[payment_id] = True  (hard_003 start)
#
# Layout (1-indexed):
#  1  : docstring
#  2  : blank
#  3  : from __future__
#  4  : blank
#  5  : import logging
#  6  : import pickle
#  7  : from typing import Optional
#  8  : blank
#  9  : from sqlalchemy.orm import Session
#  10 : from payments.models import Payment
#  11 : from payments.gateway import GatewayClient
#  12 : blank
#  13 : logger = ...
#  14 : blank
#  15 : blank
#  16 : def _generate_idempotency_key...
#  17 :     import hashlib
#  18 :     return ...
#  19 : blank
#  20 : blank
#  21 : def _build_charge_meta...
#  22 :     return ...
#  23 : blank
#  24 : blank
#  25 : class PaymentProcessor:
#  26 :     def __init__(self, session, gateway):
#  27 :         self.session = session
#  28 :         self.gateway = gateway
#  29 :         self._dup_cache: dict = {}    ← hard_004
#  30 : blank
#  31 :     def process(self, payment_id, amount, metadata=None, extra=None):
#  32 :         """Process..."""
#  33 :         if payment_id in self._dup_cache:
#  34 :             raise ValueError(...)
#  35 :         if extra is not None:          ← hard_001 start
#  36 :             parsed_extra = pickle.loads(extra)
#  37 :             (blank line / pass in real code — keep block open for 3 lines)
#  38 :         logger.info(...)              ← hard_002
#  39 :         self._dup_cache[payment_id] = True  [would be 39, but need at 41]

PROCESSOR_PY = (
    '"""payments/processor.py \u2014 Core payment processing logic."""\n'
    "\n"
    "from __future__ import annotations\n"
    "\n"
    "import logging\n"
    "import pickle\n"
    "from typing import Optional\n"
    "\n"
    "from sqlalchemy.orm import Session\n"
    "from payments.models import Payment\n"
    "from payments.gateway import GatewayClient\n"
    "\n"
    "logger = logging.getLogger(__name__)\n"
    "\n"
    "\n"
    "def _generate_idempotency_key(payment_id: str, amount: float) -> str:\n"
    "    import hashlib\n"
    "    return hashlib.sha256(f\"{payment_id}:{amount}\".encode()).hexdigest()\n"
    "\n"
    "\n"
    "def _build_charge_meta(payment_id: str, amount: float) -> dict:\n"
    '    return {"payment_id": payment_id, "amount": amount, "currency": "USD"}\n'
    "\n"
    "\n"
    "class PaymentProcessor:\n"                                    # line 25
    "    def __init__(self, session: Session, gateway: GatewayClient):\n"  # line 26
    "        self.session = session\n"                            # line 27
    "        self.gateway = gateway\n"                            # line 28
    "        self._dup_cache: dict = {}\n"                       # line 29  hard_004
    "\n"                                                           # line 30
    "    def process(\n"                                          # line 31
    "        self,\n"                                             # line 32
    "        payment_id: str,\n"                                  # line 33
    "        amount: float,\n"                                    # line 34
    "        metadata: Optional[bytes] = None,\n"                # line 35  <-- need hard_001 here
    # To fix: move the function signature to fewer lines so body starts earlier
)

# The above layout puts "metadata" at line 35 which conflicts with hard_001.
# Rethink: collapse process() signature to 1 line:
#  31:  def process(self, payment_id, amount, metadata=None, extra=None):
#  32:      """docstring"""
#  33:      if payment_id in self._dup_cache:
#  34:          raise ValueError(...)
#  35:      if extra is not None:           ← hard_001 start
#  36:          parsed_extra = pickle.loads(extra)
#  37:          log_context = {"payment_id": payment_id}  ← hard_001 line 37
#  38:      logger.info("Payment extra metadata: %s", parsed_extra)  ← hard_002
#  39:      if not self._is_duplicate(payment_id):  ← separator
#  40:          pass
#  41:      self._dup_cache[payment_id] = True   ← hard_003 start
#  42:      charge = self.gateway.charge(amount)

PROCESSOR_PY = (
    '"""payments/processor.py \u2014 Core payment processing logic."""\n'  # 1
    "\n"                                                                     # 2
    "from __future__ import annotations\n"                                  # 3
    "\n"                                                                     # 4
    "import logging\n"                                                       # 5
    "import pickle\n"                                                        # 6
    "from typing import Optional\n"                                          # 7
    "\n"                                                                     # 8
    "from sqlalchemy.orm import Session\n"                                  # 9
    "from payments.models import Payment\n"                                 # 10
    "from payments.gateway import GatewayClient\n"                         # 11
    "\n"                                                                     # 12
    "logger = logging.getLogger(__name__)\n"                               # 13
    "\n"                                                                     # 14
    "\n"                                                                     # 15
    "def _generate_idempotency_key(payment_id: str, amount: float) -> str:\n"  # 16
    "    import hashlib\n"                                                   # 17
    "    return hashlib.sha256(f\"{payment_id}:{amount}\".encode()).hexdigest()\n"  # 18
    "\n"                                                                     # 19
    "\n"                                                                     # 20
    "def _build_charge_meta(payment_id: str, amount: float) -> dict:\n"    # 21
    '    return {"payment_id": payment_id, "amount": amount, "currency": "USD"}\n'  # 22
    "\n"                                                                     # 23
    "\n"                                                                     # 24
    "class PaymentProcessor:\n"                                             # 25
    "    def __init__(self, session: Session, gateway: GatewayClient):\n"  # 26
    "        self.session = session\n"                                       # 27
    "        self.gateway = gateway\n"                                       # 28
    "        self._dup_cache: dict = {}\n"                                  # 29  hard_004
    "\n"                                                                     # 30
    "    def process(self, payment_id: str, amount: float,\n"              # 31
    "                metadata: Optional[bytes] = None, extra: Optional[bytes] = None) -> dict:\n"  # 32
    '        """Process a payment and record it in the database."""\n'     # 33
    "        if payment_id in self._dup_cache: raise ValueError(f'Duplicate {payment_id}')\n" # 34
    "        if extra is not None:\n"                                        # 35  hard_001 start
    "            parsed_extra = pickle.loads(extra)\n"                      # 36  hard_001
    '            log_context = {"payment_id": payment_id, "extra": parsed_extra}\n'  # 37  hard_001 end
    '        logger.info("Payment extra metadata: %s", parsed_extra)\n'    # 38  hard_002
    "        # duplicate guard: cache-only check (race condition)\n"        # 39
    "        _ = self._is_duplicate(payment_id)  # legacy path\n"          # 40
    "        self._dup_cache[payment_id] = True\n"                          # 41  hard_003 start
    "        charge = self.gateway.charge(amount)\n"                        # 42  hard_003 end
    "        self._record(payment_id, amount, charge)\n"                    # 43
    "        return charge\n"                                               # 44
    "\n"                                                                     # 45
    "    def _is_duplicate(self, payment_id: str) -> bool:\n"              # 46
    '        """Check DB for existing payment with this ID."""\n'           # 47
    "        return (\n"                                                     # 48
    "            self.session.query(Payment)\n"                             # 49
    "            .filter(Payment.id == payment_id)\n"                       # 50
    "            .first()\n"                                                 # 51
    "        ) is not None\n"                                               # 52
    "\n"                                                                     # 53
    "    def _record(self, payment_id: str, amount: float, charge: dict) -> None:\n"  # 54
    '        """Persist a completed payment to the database."""\n'          # 55
    "        payment = Payment(\n"                                           # 56
    "            id=payment_id,\n"                                           # 57
    "            amount=amount,\n"                                           # 58
    '            status=charge.get("status", "pending"),\n'                 # 59
    "        )\n"                                                             # 60
    "        self.session.add(payment)\n"                                    # 61
    "        self.session.commit()\n"                                        # 62
    "\n"                                                                     # 63
    "    def refund(self, payment_id: str) -> dict:\n"                      # 64
    '        """Issue a refund for an existing payment."""\n'               # 65
    "        payment = self.session.query(Payment).filter(Payment.id == payment_id).first()\n"  # 66
    "        if payment is None:\n"                                          # 67
    '            raise LookupError(f"Payment {payment_id} not found")\n'   # 68
    "        result = self.gateway.refund(payment_id)\n"                    # 69
    '        payment.status = "refunded"\n'                                 # 70
    "        self.session.commit()\n"                                        # 71
    "        return result\n"                                                # 72
)

# payments/serializers.py
# Target: include_internal block at lines 20-22
# Layout:
#   1 : docstring
#   2 : blank
#   3 : from __future__
#   4 : blank
#   5 : from payments.models import Payment
#   6 : blank
#   7 : blank
#   8 : class PaymentSerializer:
#   9 :     def __init__(self, payment, include_internal=False):
#  10 :         self.payment = payment
#  11 :         self.include_internal = include_internal
#  12 : blank
#  13 :     def to_dict(self, requester_role="user") -> dict:
#  14 :         data = {
#  15 :             "id": ...
#  16 :             "amount": ...
#  17 :             "status": ...
#  18 :             "created_at": ...
#  19 :         }
#  20 :         if self.include_internal:            ← hard_005 start
#  21 :             data["customer_ssn_last4"] = ...
#  22 :             data["internal_ref"] = ...       ← hard_005 end
#  23 :         return data

SERIALIZERS_PY = (
    '"""payments/serializers.py \u2014 Serialisation helpers for Payment objects."""\n'  # 1
    "\n"                                                                               # 2
    "from __future__ import annotations\n"                                            # 3
    "\n"                                                                               # 4
    "from payments.models import Payment\n"                                           # 5
    "\n"                                                                               # 6
    "\n"                                                                               # 7
    "class PaymentSerializer:\n"                                                      # 8
    "    def __init__(self, payment: Payment, include_internal: bool = False):\n"    # 9
    "        self.payment = payment\n"                                                # 10
    "        self.include_internal = include_internal\n"                              # 11
    "\n"                                                                               # 12
    '    def to_dict(self, requester_role: str = "user") -> dict:\n'                 # 13
    "        data = {\n"                                                               # 14
    '            "id":         self.payment.id,\n'                                   # 15
    '            "amount":     float(self.payment.amount),\n'                        # 16
    '            "status":     self.payment.status,\n'                               # 17
    '            "created_at": self.payment.created_at.isoformat(),\n'              # 18
    "        }\n"                                                                      # 19
    "        if self.include_internal:\n"                                             # 20  hard_005 start
    '            data["customer_ssn_last4"] = self.payment.customer_ssn_last4\n'    # 21
    '            data["internal_ref"]       = self.payment.internal_ref\n'          # 22  hard_005 end
    "        return data\n"                                                            # 23
    "\n"                                                                               # 24
    "    def to_summary(self) -> dict:\n"                                             # 25
    '        """Return a minimal public summary of the payment."""\n'                # 26
    "        return {\n"                                                               # 27
    '            "id":     self.payment.id,\n'                                       # 28
    '            "status": self.payment.status,\n'                                   # 29
    "        }\n"                                                                      # 30
)

# payments/api.py
# Target: is_admin at line 30, serializer at line 31
# Layout:
#   1-18: imports
#   19  : logger = ...
#   20  : router = ...
#   21  : blank
#   22  : blank
#   23  : class PaymentRequest(BaseModel):
#   24  :     amount: float
#   25  :     currency: str = "USD"
#   26  :     metadata: dict = {}
#   27  :     is_admin: bool = False
#   28  : blank
#   29  : blank
#   30  : is_admin = request.is_admin      ← hard_006 start (but this is inside function!)
# Wait: hard_006 is about lines 30-31 inside the function. The @router.post decorator
# and async def must come before line 30. So:
#   23  : @router.post("/payments")
#   24  : async def create_payment(
#   25  :     request: PaymentRequest,
#   26  :     background_tasks: BackgroundTasks,
#   27  :     db: Session = Depends(get_db),
#   28  : ):
#   29  :     """Create...""" or just blank
#   30  :     is_admin = request.is_admin       ← hard_006 start
#   31  :     serializer = PaymentSerializer(...)← hard_006 end
# This means PaymentRequest must be defined above line 23.
# Imports 1-20, PaymentRequest 21-22 (inline 1-liner won't work for Pydantic).
# Let me try: compact imports so PaymentRequest ends by line 20, route starts at 21:

API_PY = (
    '"""payments/api.py \u2014 FastAPI router for the payments service."""\n'  # 1
    "\n"                                                                        # 2
    "from __future__ import annotations\n"                                     # 3
    "import logging\n"                                                          # 4
    "from uuid import uuid4\n"                                                  # 5
    "from fastapi import APIRouter, BackgroundTasks, Depends\n"                # 6
    "from pydantic import BaseModel\n"                                          # 7
    "from sqlalchemy.orm import Session\n"                                      # 8
    "from payments.gateway import gateway_client\n"                            # 9
    "from payments.models import Payment\n"                                     # 10
    "from payments.processor import PaymentProcessor\n"                        # 11
    "from payments.serializers import PaymentSerializer\n"                     # 12
    "from db import get_db\n"                                                   # 13
    "from audit import audit_log\n"                                             # 14
    "\n"                                                                        # 15
    "logger = logging.getLogger(__name__)\n"                                   # 16
    "router = APIRouter()\n"                                                    # 17
    "\n"                                                                        # 18
    "\n"                                                                        # 19
    "class PaymentRequest(BaseModel):\n"                                       # 20
    "    amount: float\n"                                                       # 21
    '    currency: str = "USD"\n'                                              # 22
    "    metadata: dict = {}\n"                                                 # 23
    "    is_admin: bool = False\n"                                              # 24
    "\n"                                                                        # 25
    "\n"                                                                        # 26
    '@router.post("/payments")\n'                                              # 27
    "async def create_payment(\n"                                               # 28
    "    request: PaymentRequest,\n"                                            # 29
    "    background_tasks: BackgroundTasks,\n"                                  # 30  ← need is_admin here
    # This puts background_tasks at 30. Need is_admin at 30. Collapse func args:
)

# Try: put the entire function signature on 1 line so body starts at line 29:
API_PY = (
    '"""payments/api.py \u2014 FastAPI router for the payments service."""\n'  # 1
    "\n"                                                                        # 2
    "from __future__ import annotations\n"                                     # 3
    "import logging\n"                                                          # 4
    "from uuid import uuid4\n"                                                  # 5
    "from fastapi import APIRouter, BackgroundTasks, Depends\n"                # 6
    "from pydantic import BaseModel\n"                                          # 7
    "from sqlalchemy.orm import Session\n"                                      # 8
    "from payments.gateway import gateway_client\n"                            # 9
    "from payments.models import Payment\n"                                     # 10
    "from payments.processor import PaymentProcessor\n"                        # 11
    "from payments.serializers import PaymentSerializer\n"                     # 12
    "from db import get_db\n"                                                   # 13
    "from audit import audit_log\n"                                             # 14
    "\n"                                                                        # 15
    "logger = logging.getLogger(__name__)\n"                                   # 16
    "router = APIRouter()\n"                                                    # 17
    "\n"                                                                        # 18
    "\n"                                                                        # 19
    "class PaymentRequest(BaseModel):\n"                                       # 20
    "    amount: float\n"                                                       # 21
    '    currency: str = "USD"\n'                                              # 22
    "    metadata: dict = {}\n"                                                 # 23
    "    is_admin: bool = False\n"                                              # 24
    "\n"                                                                        # 25
    "\n"                                                                        # 26
    '@router.post("/payments")\n'                                              # 27
    "async def create_payment(request: PaymentRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):\n"  # 28
    '    """Process and record a new payment."""\n'                            # 29
    "    is_admin = request.is_admin\n"                                        # 30  hard_006 start
    "    serializer = PaymentSerializer(payment=None, include_internal=is_admin)\n"  # 31  hard_006 end
    "    processor = PaymentProcessor(session=db, gateway=gateway_client)\n"  # 32
    "    result = processor.process(\n"                                         # 33
    "        payment_id=str(uuid4()),\n"                                        # 34
    "        amount=request.amount,\n"                                          # 35
    "        metadata=None,\n"                                                  # 36
    "    )\n"                                                                    # 37
    "    background_tasks.add_task(audit_log, result)\n"                       # 38
    "    payment = Payment(**result)\n"                                         # 39
    "    return serializer.to_dict()\n"                                         # 40
    "\n"                                                                        # 41
    "\n"                                                                        # 42
    '@router.get("/payments/{payment_id}")\n'                                  # 43
    "async def get_payment(payment_id: str, db: Session = Depends(get_db)):\n"  # 44
    '    """Retrieve a payment by ID."""\n'                                     # 45
    "    payment = db.query(Payment).filter(Payment.id == payment_id).first()\n"  # 46
    "    if payment is None:\n"                                                  # 47
    "        from fastapi import HTTPException\n"                                # 48
    "        raise HTTPException(status_code=404, detail=\"Payment not found\")\n"  # 49
    "    return PaymentSerializer(payment).to_dict()\n"                         # 50
    "\n"                                                                        # 51
    "\n"                                                                        # 52
    '@router.delete("/payments/{payment_id}")\n'                               # 53
    "async def cancel_payment(payment_id: str, db: Session = Depends(get_db)):\n"  # 54
    '    """Cancel a pending payment."""\n'                                     # 55
    "    processor = PaymentProcessor(session=db, gateway=gateway_client)\n"  # 56
    "    result = processor.refund(payment_id)\n"                               # 57
    "    return result\n"                                                        # 58
)

# payments/models.py
# Target: Float column at line 9
# Layout:
#   1: docstring
#   2: blank
#   3: from datetime import datetime
#   4: from uuid import uuid4
#   5: from sqlalchemy import Column, DateTime, Float, String
#   6: from sqlalchemy.orm import declarative_base
#   7: blank
#   8: Base = declarative_base()
#   9: (blank or first column)
#
# To have Float column at line 9, the Payment class must start at line 6 or earlier.
# Try: no `Base = declarative_base()` line before the class, or make Payment class start at line 6.
# Actually: if class starts at line 6 with no Base line, columns at 7+.
# Simpler: put the Float column as the SECOND column (after id), which means:
#   6: class Payment(Base):
#   7:     __tablename__ = "payments"
#   8:     id = Column(String, ...)
#   9:     amount = Column(Float, ...)   ← hard_007

MODELS_PY = (
    '"""payments/models.py \u2014 SQLAlchemy ORM models for the payments service."""\n'  # 1
    "from datetime import datetime\n"                                                      # 2
    "from uuid import uuid4\n"                                                             # 3
    "from sqlalchemy import Column, DateTime, Float, String\n"                            # 4
    "from sqlalchemy.orm import declarative_base\n"                                       # 5
    "Base = declarative_base()\n"                                                          # 6
    "class Payment(Base):\n"                                                               # 7
    '    __tablename__ = "payments"\n'                                                     # 8
    "    amount             = Column(Float, nullable=False)\n"                             # 9  hard_007
    "    id                 = Column(String, primary_key=True, default=lambda: str(uuid4()))\n"  # 10
    '    status             = Column(String, default="pending")\n'                        # 11
    "    created_at         = Column(DateTime, default=datetime.utcnow)\n"                # 12
    "    customer_ssn_last4 = Column(String(4), nullable=True)\n"                         # 13
    "    internal_ref       = Column(String, nullable=True)\n"                            # 14
    "\n"                                                                                    # 15
    "    def __repr__(self) -> str:\n"                                                     # 16
    '        return f"<Payment id={self.id} amount={self.amount} status={self.status}>"\n'  # 17
    "\n"                                                                                    # 18
    "    @property\n"                                                                       # 19
    "    def is_completed(self) -> bool:\n"                                                # 20
    '        return self.status == "completed"\n'                                          # 21
    "\n"                                                                                    # 22
    "    @property\n"                                                                       # 23
    "    def is_refunded(self) -> bool:\n"                                                 # 24
    '        return self.status == "refunded"\n'                                           # 25
    "\n"                                                                                    # 26
    "    def to_minimal_dict(self) -> dict:\n"                                             # 27
    '        """Return a minimal public representation."""\n'                              # 28
    '        return {"id": self.id, "status": self.status}\n'                             # 29
    "\n"                                                                                    # 30
    "    def mark_completed(self) -> None:\n"                                              # 31
    '        """Transition status to completed."""\n'                                      # 32
    '        self.status = "completed"\n'                                                   # 33
    "\n"                                                                                    # 34
    "    def mark_refunded(self) -> None:\n"                                               # 35
    '        """Transition status to refunded."""\n'                                       # 36
    '        self.status = "refunded"\n'                                                   # 37
)

# config/logging_config.py
# Target: hardcoded /tmp/payments.log filename at line 12
# Layout:
#   1 : docstring
#   2 : blank
#   3 : import logging.config
#   4 : blank
#   5 : blank
#   6 : LOGGING = {
#   7 :     "version": 1,
#   8 :     "disable_existing_loggers": False,
#   9 :     "handlers": {
#  10 :         "file": {
#  11 :             "class": "logging.FileHandler",
#  12 :             "filename": "/tmp/payments.log"    ← hard_008
#  13 :         },

LOGGING_CONFIG_PY = (
    '"""config/logging_config.py \u2014 Application-wide logging configuration."""\n'  # 1
    "\n"                                                                                  # 2
    "import logging.config\n"                                                             # 3
    "\n"                                                                                  # 4
    "\n"                                                                                  # 5
    "LOGGING = {\n"                                                                       # 6
    '    "version": 1,\n'                                                                 # 7
    '    "disable_existing_loggers": False,\n'                                           # 8
    '    "handlers": {\n'                                                                 # 9
    '        "file": {\n'                                                                 # 10
    '            "class": "logging.FileHandler",\n'                                      # 11
    '            "filename": "/tmp/payments.log",\n'                                     # 12  hard_008
    "        },\n"                                                                        # 13
    '        "console": {\n'                                                              # 14
    '            "class": "logging.StreamHandler",\n'                                    # 15
    '            "formatter": "standard",\n'                                             # 16
    "        },\n"                                                                        # 17
    "    },\n"                                                                            # 18
    '    "formatters": {\n'                                                               # 19
    '        "standard": {\n'                                                             # 20
    '            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",\n'      # 21
    '            "datefmt": "%Y-%m-%dT%H:%M:%S",\n'                                     # 22
    "        }\n"                                                                          # 23
    "    },\n"                                                                            # 24
    '    "root": {\n'                                                                     # 25
    '        "level": "INFO",\n'                                                          # 26
    '        "handlers": ["file", "console"],\n'                                         # 27
    "    },\n"                                                                            # 28
    '    "loggers": {\n'                                                                  # 29
    '        "payments": {\n'                                                             # 30
    '            "level": "DEBUG",\n'                                                     # 31
    '            "handlers": ["file"],\n'                                                 # 32
    '            "propagate": False,\n'                                                   # 33
    "        }\n"                                                                          # 34
    "    },\n"                                                                            # 35
    "}\n"                                                                                  # 36
    "\n"                                                                                  # 37
    "\n"                                                                                  # 38
    "def configure_logging() -> None:\n"                                                  # 39
    '    """Apply the logging configuration to the running process."""\n'                # 40
    "    logging.config.dictConfig(LOGGING)\n"                                            # 41
)

# ---------------------------------------------------------------------------
# Ground truth — 8 issues, 4 critical
# ---------------------------------------------------------------------------

GROUND_TRUTH = [
    GroundTruthIssue(
        file="payments/processor.py",
        line_start=35,
        line_end=37,
        category="security",
        severity="critical",
        cwe_id="CWE-502",
        description="pickle.loads on user bytes enables RCE",
        issue_id="hard_001",
        is_critical=True,
    ),
    GroundTruthIssue(
        file="payments/processor.py",
        line_start=38,
        line_end=38,
        category="security",
        severity="high",
        cwe_id="CWE-532",
        description="Sensitive deserialized data written to logs",
        issue_id="hard_002",
        is_critical=False,
    ),
    GroundTruthIssue(
        file="payments/processor.py",
        line_start=41,
        line_end=42,
        category="bug",
        severity="high",
        cwe_id="",
        description=(
            "In-memory cache replaces DB duplicate check, "
            "race condition across workers"
        ),
        issue_id="hard_003",
        is_critical=True,
    ),
    GroundTruthIssue(
        file="payments/processor.py",
        line_start=29,
        line_end=29,
        category="bug",
        severity="medium",
        cwe_id="",
        description="Unbounded cache dict causes memory leak",
        issue_id="hard_004",
        is_critical=False,
    ),
    GroundTruthIssue(
        file="payments/serializers.py",
        line_start=20,
        line_end=22,
        category="security",
        severity="critical",
        cwe_id="CWE-200",
        description="customer_ssn_last4 exposed via include_internal",
        issue_id="hard_005",
        is_critical=True,
    ),
    GroundTruthIssue(
        file="payments/api.py",
        line_start=30,
        line_end=31,
        category="security",
        severity="high",
        cwe_id="CWE-862",
        description="is_admin trusted from client request body",
        issue_id="hard_006",
        is_critical=True,
    ),
    GroundTruthIssue(
        file="payments/models.py",
        line_start=9,
        line_end=9,
        category="bug",
        severity="medium",
        cwe_id="",
        description="Float for monetary amount causes rounding errors",
        issue_id="hard_007",
        is_critical=False,
    ),
    GroundTruthIssue(
        file="config/logging_config.py",
        line_start=12,
        line_end=12,
        category="style",
        severity="low",
        cwe_id="",
        description="Hardcoded log path not portable across environments",
        issue_id="hard_008",
        is_critical=False,
    ),
]

# ---------------------------------------------------------------------------
# Task definition
# ---------------------------------------------------------------------------

HARD_TASK = TaskDefinition(
    task_id="hard",
    name="Payment Processor Security & Bug Audit",
    difficulty="hard",
    description=(
        "A payment processing PR introduces RCE via pickle, a log-injection "
        "vulnerability, a cache-based race condition, an IDOR via client-supplied "
        "is_admin, SSN exposure in the serializer, Float for monetary columns, "
        "and a hardcoded log path. Requires up to 3 review passes."
    ),
    diff=DIFF,
    file_contexts={
        "payments/processor.py":    PROCESSOR_PY,
        "payments/serializers.py":  SERIALIZERS_PY,
        "payments/api.py":          API_PY,
        "payments/models.py":       MODELS_PY,
        "config/logging_config.py": LOGGING_CONFIG_PY,
    },
    ground_truth=GROUND_TRUTH,
    max_steps=3,
    pr_title="Payment processor performance improvements",
    pr_description=(
        "Adds metadata support, caches duplicate checks in memory for speed, "
        "exposes internal fields for admin users, updates amount storage to decimal"
    ),
)
