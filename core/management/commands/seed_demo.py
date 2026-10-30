"""Create demo data: products, capstone projects, sample customer comments, an admin and a demo customer.

Safe to run more than once: existing records (matched by slug/email) are left alone.
"""

import io
import zipfile
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw, ImageFont

from capstone.models import CapstoneProject
from catalog.models import Product
from core.models import SiteSettings, Testimonial

# Sample content for local demos only; replace with real customer comments before launch.
DEMO_TESTIMONIALS = [
    {
        "name": "Maricel Santos",
        "role": "Owner, Santos Pharmacy — Batangas",
        "rating": 5,
        "is_featured": True,
        "message": "InventoryPro replaced our notebook inventory. The low-stock alerts alone saved us from running "
                   "out of maintenance medicines twice this month, and setup took one afternoon.",
    },
    {
        "name": "Paolo Reyes",
        "role": "BSIT student, PUP Manila",
        "rating": 5,
        "is_featured": True,
        "message": "Our group requested the thesis archive system with an added adviser approval module. The quote "
                   "was clear, the walkthrough call helped us answer the panel's questions, and we passed.",
    },
    {
        "name": "Angelica Cruz",
        "role": "BSCS student, University of Batangas",
        "rating": 5,
        "message": "Paid through GCash in the evening and my download was unlocked the next morning. The "
                   "documentation explained every module, so customising it for our school was easy.",
    },
    {
        "name": "Jerome Villanueva",
        "role": "Freelance web developer, Cebu",
        "rating": 4,
        "message": "Clean code that is easy to extend. I used ClinicFlow as the base for a client's dental "
                   "clinic and only needed to change the branding and add SMS reminders.",
    },
    {
        "name": "Kristine Mendoza",
        "role": "Registrar staff, St. Therese Academy",
        "rating": 5,
        "message": "We use SchoolPay to track tuition installments for our small school. When we had trouble "
                   "printing statements, support replied within the hour and fixed it with us over a call.",
    },
    {
        "name": "Mark Anthony Lim",
        "role": "BSIS student, STI College",
        "rating": 4,
        "message": "Our barangay health records capstone built on the first try in Android Studio. Messaging the "
                   "team from the request page made it easy to track what was being added for our defense.",
    },
]

PRODUCTS = [
    {
        "name": "InventoryPro POS",
        "category": Product.Category.SOFTWARE,
        "price": "2499.00",
        "version": "3.2.0",
        "tech_stack": "Python, PySide6, SQLite",
        "short_description": "Point-of-sale and inventory system for sari-sari stores, pharmacies and small retail shops.",
        "description": "InventoryPro POS keeps your stock, sales and receipts in one fast desktop app that works even without internet.\n\nScan barcodes, print receipts on 58 mm thermal printers, and see which items are running low before they run out. End-of-day reports show exactly how much you earned.",
        "features": "Barcode scanning and thermal receipt printing\nLow-stock alerts\nDaily, weekly and monthly sales reports\nMultiple cashier accounts with roles\nWorks offline; one-click database backup",
        "is_featured": True,
        "colors": ("#4f46e5", "#7c3aed"),
    },
    {
        "name": "BarangayConnect Mobile",
        "category": Product.Category.MOBILE_APP,
        "price": "2999.00",
        "version": "1.4.0",
        "tech_stack": "Flutter, Firebase",
        "short_description": "Android app for barangay announcements, document requests and incident reports.",
        "description": "BarangayConnect brings barangay services to residents' phones. Residents can request clearances and certificates, receive announcements, and report incidents with photos.\n\nOfficials manage everything from a simple admin panel, and residents get push notifications when their documents are ready.",
        "features": "Document requests with status tracking\nPush-notification announcements\nIncident reports with photos and location\nResident verification\nAdmin panel for officials",
        "is_featured": True,
        "colors": ("#10b981", "#0ea5e9"),
    },
    {
        "name": "QuickInvoice Desktop",
        "category": Product.Category.SOFTWARE,
        "price": "1499.00",
        "version": "4.1.0",
        "tech_stack": "C#, .NET 8, WinForms",
        "short_description": "Create professional invoices and quotations in under a minute, then save them as PDF.",
        "description": "QuickInvoice is a lightweight Windows app for freelancers and small businesses. Keep a customer list, reuse line items, and export polished PDF invoices with your logo.",
        "features": "Invoices and quotations with your logo\nCustomer and item lists\nPDF export and email-ready files\nVAT and discount support\nPaid / unpaid tracking",
        "is_featured": False,
        "colors": ("#6366f1", "#ec4899"),
    },
    {
        "name": "FitTrack Workout Planner",
        "category": Product.Category.MOBILE_APP,
        "price": "1299.00",
        "version": "2.3.0",
        "tech_stack": "Kotlin, Jetpack Compose, Room",
        "short_description": "Plan workouts, log sets and watch your progress with simple charts — fully offline.",
        "description": "FitTrack is a clean Android workout planner. Build routines, log every set, and see your strength progress over time. Everything is stored on the device.",
        "features": "Custom routines and exercise library\nSet, rep and weight logging\nProgress charts\nRest timer\nOffline-first, no account needed",
        "is_featured": False,
        "colors": ("#14b8a6", "#22c55e"),
    },
    {
        "name": "Library Kiosk (Preview)",
        "category": Product.Category.SOFTWARE,
        "price": "2199.00",
        "version": "0.9.0",
        "tech_stack": "Electron, Vue, SQLite",
        "short_description": "Self-service borrowing kiosk for school libraries. Still in testing — saved as a draft.",
        "description": "A draft product used to show that unpublished items never appear on the store.",
        "features": "Self-service borrowing\nRFID ready",
        "is_featured": False,
        "status": Product.Status.DRAFT,
        "colors": ("#64748b", "#334155"),
    },
]

CAPSTONE_PROJECTS = [
    {
        "title": "Web-Based Thesis Archive with Similarity Checker",
        "field": CapstoneProject.Field.WEB,
        "suggested_price": "15000.00",
        "tech_stack": "Django, PostgreSQL, Bootstrap, React",
        "short_description": "Digital repository for research papers with a built-in similarity checker for new submissions.",
        "description": "A complete research repository for colleges. Students upload their manuscripts, advisers approve them, and the system compares new titles and abstracts against the archive to flag similar studies.\n\nIdeal for BSIT and BSCS groups who want a system with a real algorithm component (TF-IDF and cosine similarity).",
        "features": "Role-based access: student, adviser, librarian, admin\nTitle and abstract similarity checking (TF-IDF)\nAdvanced search by year, program and keyword\nApproval workflow with comments\nPDF viewer with download restrictions\nAnalytics dashboard",
        "with_docs": True,
        "colors": ("#4f46e5", "#0ea5e9"),
    },
    {
        "title": "IoT Water Level Monitoring with SMS Alerts",
        "field": CapstoneProject.Field.IOT,
        "suggested_price": "18000.00",
        "tech_stack": "Flask, C#, MySQL",
        "short_description": "Real-time flood and tank water-level monitoring with automatic SMS warnings to residents.",
        "description": "Ultrasonic sensors on an ESP32 send water-level readings to a web dashboard every few seconds. When the level crosses a threshold, the system sends SMS alerts to registered residents and officials.\n\nIncludes the hardware wiring diagram, firmware and the web dashboard.",
        "features": "ESP32 firmware with Wi-Fi reconnect\nLive water-level dashboard and history charts\nConfigurable alert thresholds\nSMS alerts via GSM module or SMS API\nResident registration and alert groups",
        "with_docs": False,
        "colors": ("#0ea5e9", "#10b981"),
    },
    {
        "title": "Mobile Barangay Health Records System",
        "field": CapstoneProject.Field.MOBILE,
        "suggested_price": "16000.00",
        "tech_stack": "Flutter, Firebase, Node.js",
        "short_description": "Health workers record check-ups, immunizations and prenatal visits on a phone, even offline.",
        "description": "Designed for barangay health workers, this app replaces paper logbooks. Records sync to the cloud when a connection is available, and the midwife's dashboard shows upcoming immunizations and overdue visits.",
        "features": "Offline-first data entry with sync\nImmunization schedule tracking\nPrenatal and check-up records\nReports for the municipal health office\nRole-based access for BHWs and midwives",
        "with_docs": True,
        "colors": ("#ec4899", "#8b5cf6"),
    },
    {
        "title": "ClinicFlow Appointment System",
        "field": CapstoneProject.Field.WEB,
        "suggested_price": "3499.00",
        "tech_stack": "Django, PostgreSQL, Bootstrap 5",
        "short_description": "Online booking, patient records and SMS-ready reminders for clinics and dental offices.",
        "description": "ClinicFlow lets patients book appointments online while your staff manage schedules, patient records and payments from one dashboard.\n\nIt ships with a clean responsive interface, role-based access for doctors and front-desk staff, and printable patient summaries.",
        "features": "Online booking with available time slots\nPatient records and visit history\nDoctor and staff roles\nPrintable patient summary\nEmail reminders (SMS gateway ready)",
        "with_docs": False,
        "colors": ("#0ea5e9", "#4f46e5"),
    },
    {
        "title": "SchoolPay Fee Tracker",
        "field": CapstoneProject.Field.WEB,
        "suggested_price": "1999.00",
        "tech_stack": "Flask, MySQL, Tailwind CSS",
        "short_description": "Track tuition and miscellaneous fees, print statements, and see who still has a balance.",
        "description": "SchoolPay helps school cashiers record payments, issue official receipts and generate statements of account in seconds.\n\nParents can view balances online, and the registrar can export collection reports per term.",
        "features": "Student ledger and statement of account\nOfficial receipt printing\nCollection reports per term\nParent portal for balances\nExcel export",
        "with_docs": False,
        "colors": ("#f59e0b", "#ef4444"),
    },
]


def make_thumbnail(title, subtitle, colors):
    width, height = 1280, 800
    img = Image.new("RGB", (width, height), colors[0])
    start = Image.new("RGB", (1, 1), colors[0]).getpixel((0, 0))
    end = Image.new("RGB", (1, 1), colors[1]).getpixel((0, 0))
    draw = ImageDraw.Draw(img)
    for x in range(width):
        t = x / width
        draw.line([(x, 0), (x, height)], fill=tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3)))
    # soft decorative circles
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    o = ImageDraw.Draw(overlay)
    o.ellipse((850, -200, 1500, 450), fill=(255, 255, 255, 30))
    o.ellipse((-200, 500, 400, 1100), fill=(255, 255, 255, 22))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        big = ImageFont.load_default(size=72)
        small = ImageFont.load_default(size=36)
    except TypeError:  # very old Pillow
        big = small = ImageFont.load_default()
    draw.text((90, 300), title, font=big, fill="white")
    draw.text((92, 400), subtitle, font=small, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return ContentFile(buf.getvalue(), name="thumbnail.png")


def make_zip(name, version, features):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.md",
            f"# {name} v{version}\n\nThank you for your purchase!\n\n## Features\n"
            + "".join(f"- {f}\n" for f in features.splitlines())
            + "\n## Setup\n1. Extract this archive.\n2. Follow INSTALL.txt.\n3. Message us from your account if you need help.\n",
        )
        zf.writestr("INSTALL.txt", "Installation steps are included with the full release package.\n")
        zf.writestr("LICENSE.txt", "Single-user licence. Do not redistribute.\n")
    return ContentFile(buf.getvalue(), name="package.zip")


def make_pdf_placeholder(title):
    """Tiny valid PDF so the documentation download works in the demo."""
    text = f"{title} - Documentation (demo)".replace("(", "[").replace(")", "]")
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{obj}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return ContentFile(out.getvalue(), name="documentation.pdf")


class Command(BaseCommand):
    help = "Create demo products, capstone projects, an admin user and a demo customer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Admin2026!",
            help="Password for the two demo accounts (admin@example.com and demo@example.com).",
        )
        parser.add_argument(
            "--reset-all-passwords",
            action="store_true",
            help="Local development only: also set this password on every other existing account.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # The demo accounts use a password published in the README; never create them on a live site.
        if not settings.DEBUG:
            raise CommandError("seed_demo creates accounts with a published password and only runs when DEBUG=True.")
        User = get_user_model()
        password = options["password"]

        demo_users = [
            User.objects.get_or_create(
                email="admin@example.com",
                defaults={"first_name": "Store", "last_name": "Admin",
                          "is_staff": True, "is_superuser": True},
            )[0],
            User.objects.get_or_create(
                email="demo@example.com",
                defaults={"first_name": "Juan", "last_name": "Dela Cruz",
                          "school": "Polytechnic University of the Philippines", "phone_number": "+63 917 555 0101"},
            )[0],
        ]

        targets = User.objects.all() if options["reset_all_passwords"] else demo_users
        updated = 0
        for user in targets:
            user.set_password(password)
            user.save(update_fields=["password"])
            updated += 1
            self.stdout.write(self.style.SUCCESS(f"Password set: {user.email}"))
        self.stdout.write(self.style.SUCCESS(f"{updated} user account(s) now use the shared demo password."))

        for data in PRODUCTS:
            data = dict(data)
            colors = data.pop("colors")
            if Product.objects.filter(name=data["name"]).exists():
                continue
            product = Product(status=data.pop("status", Product.Status.PUBLISHED), **data)
            product.price = Decimal(product.price)
            product.thumbnail.save("thumb.png", make_thumbnail(product.name, product.get_category_display(), colors), save=False)
            product.file.save("package.zip", make_zip(product.name, product.version, product.features), save=False)
            product.save()
            self.stdout.write(f"  + product: {product.name} ({product.get_status_display()})")

        for data in CAPSTONE_PROJECTS:
            data = dict(data)
            colors = data.pop("colors")
            with_docs = data.pop("with_docs")
            if CapstoneProject.objects.filter(title=data["title"]).exists():
                continue
            project = CapstoneProject(status=CapstoneProject.Status.PUBLISHED, **data)
            project.suggested_price = Decimal(project.suggested_price)
            project.thumbnail.save("thumb.png", make_thumbnail("Capstone Project", project.get_field_display(), colors), save=False)
            project.source_code.save("source.zip", make_zip(project.title, "1.0", project.features), save=False)
            if with_docs:
                project.documentation.save("docs.pdf", make_pdf_placeholder(project.title), save=False)
            project.save()
            self.stdout.write(f"  + capstone project: {project.title}")

        added = 0
        for data in DEMO_TESTIMONIALS:
            _, created = Testimonial.objects.get_or_create(
                name=data["name"], user=None,
                defaults={**data, "status": Testimonial.Status.APPROVED},
            )
            added += created
        if added:
            self.stdout.write(self.style.WARNING(
                f"  ! Added {added} SAMPLE customer comments for the demo. Delete them in /manage/testimonials/ "
                "before going live — only publish comments from real customers."
            ))

        site = SiteSettings.objects.get_or_create(pk=1)[0]
        if not site.gcash_number and not site.gcash_qr:
            site.gcash_account_name = "FaintedBrain Digital"
            site.gcash_number = "0917 000 0000"
            site.save()
            self.stdout.write(self.style.WARNING(
                "  ! Demo GCash number set to 0917 000 0000 — change it in /manage/settings/ before going live."
            ))

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
