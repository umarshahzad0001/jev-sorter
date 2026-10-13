"""Starter category packs for the Categories page. Jev reads the descriptions, not
just the names, so each one says what lands in the folder, with the filename
patterns and extensions that give it away."""

PACKS: dict[str, list[tuple[str, str]]] = {
    "Downloads cleanup": [
        ("Documents", "Word, PDF and text documents: letters, forms, manuals, notes and scanned pages. .pdf .docx .doc .txt .rtf."),
        ("Spreadsheets", "Excel and CSV files: exports, lists, ledgers and calculations. .xlsx .xls .csv."),
        ("Presentations", "Slide decks: pitch decks, training slides and talks. .pptx .ppt .key."),
        ("Images", "Photos and graphics, not screenshots: IMG_*, DSC_*, WhatsApp Image *, .jpg .jpeg .png .webp .heic .gif .svg."),
        ("Screenshots", "Screen captures: Screenshot_*, Screenshot *, Screen Shot *, Snip*, Capture*, usually .png."),
        ("Videos", "Video clips and recordings, including screen recordings. .mp4 .mov .mkv .avi .webm."),
        ("Audio", "Music, voice notes and podcast episodes. .mp3 .wav .m4a .flac .ogg, WhatsApp Audio *."),
        ("Installers", "Setup programs and software packages, often with a version number: setup, installer, .exe .msi .msix .dmg .apk."),
        ("Archives", "Compressed bundles and backups: .zip .rar .7z .tar .gz."),
        ("Ebooks", "Books for reading: .epub .mobi .azw3, and PDFs of whole books or textbooks."),
        ("Fonts and design files", "Fonts and design sources: .ttf .otf .woff, .psd .ai .fig .sketch .xd."),
    ],
    "Work and office": [
        ("Invoices", "Sales and purchase invoices with a number or date in the name: INV-*, Invoice_*, Bill_*, a client or supplier name plus a month."),
        ("Receipts", "Proof of payment: receipt, payment confirmation, voucher, till slip, order confirmation. Often a small PDF or a photo."),
        ("Contracts and agreements", "Signed or draft legal documents: contract, agreement, NDA, MOU, terms, lease, offer letter, addendum."),
        ("Quotes and proposals", "Offers sent before a sale or project: quotation, quote, proposal, estimate, tender, pricing sheet."),
        ("Meeting notes", "Minutes, agendas and action lists, usually dated: meeting, minutes, MoM, agenda, call notes."),
        ("Reports", "Finished reports and analysis meant for reading: monthly report, summary, review, whitepaper, dashboard export."),
        ("HR and payroll", "Staff records: payslip, salary sheet, attendance, leave, timesheet, CV, resume, onboarding form."),
        ("Tax and compliance", "Tax returns, challans, withholding statements, registration certificates and regulator filings."),
        ("Bank statements", "Bank, card and wallet statements: statement, account activity, bank advice, with a month or date range."),
        ("Client material", "Files that belong to one named client: briefs, logos, requirement documents and handover packs."),
    ],
    "Accounting and finance": [
        ("General ledgers", "Account-by-account transaction listings: general ledger, GL, account ledger, partner ledger, usually with a date range in the name."),
        ("Trial balances", "Trial balance, TB, adjusted trial balance, balance sheet, income statement, P&L, financial statements."),
        ("Bank reconciliations", "Bank reconciliation, BRS, cash book, bank book, reconciled statements and lists of unreconciled items."),
        ("Invoices issued", "Documents sent to customers: sales invoice, tax invoice, credit note, debit note, delivery challan."),
        ("Bills received", "Supplier bills to pay: bill, purchase invoice, vendor invoice, supplier statement."),
        ("Payroll", "Payroll registers, payslips, salary sheets, provident fund and social security returns, withholding on salary."),
        ("Tax filings", "Income tax, sales tax and withholding returns, challans, tax notices and assessment orders."),
        ("Audit working papers", "Audit files: working paper, WP, lead schedule, confirmation, sample, checklist, management letter, audit report."),
        ("Budgets and forecasts", "Budget, forecast, cash flow projection, variance analysis and financial models."),
        ("Fixed assets", "Asset registers, depreciation schedules, capex lists and disposal records."),
    ],
    "Software projects": [
        ("Source code", "Code and project bundles: .py .js .ts .java .cs .php files and zipped repositories with project or repo in the name."),
        ("Design assets", "Screens and brand assets for products: mockup, wireframe, logo, icon, banner, .fig .sketch .svg."),
        ("API and docs", "Technical documentation: API reference, README, spec, openapi, swagger, postman collection, architecture notes."),
        ("Logs and dumps", "Log files, crash dumps, stack traces and debug output: .log, traceback, trace, dump."),
        ("Database exports", "Database backups and data exports: .sql .dump .bak .sqlite .db, dump_*, backup_*."),
        ("Config files", "Configuration: .env .json .yaml .yml .toml .ini .conf, docker-compose, settings."),
        ("Datasets", "Data for analysis or testing: .csv .parquet .jsonl, sample data, seed data, training data."),
        ("Tools and runtimes", "Developer tools, SDKs, drivers and runtimes: sdk, jdk, node, python, docker, vscode installers .exe .msi .zip."),
        ("Diagrams", "Diagrams and exported charts: .drawio .puml .mmd, flowchart, ERD, architecture diagram."),
    ],
    "Photos and media": [
        ("Camera photos", "Photos straight from a phone or camera: IMG_1234, DSC_0001, PXL_*, 20240101_123456.jpg, .heic .jpg .dng."),
        ("Screenshots", "Screen captures: Screenshot_*, Screenshot *, Screen Shot *, Snip*, Capture*."),
        ("Chat media", "Media received through messaging apps: WhatsApp Image *, WhatsApp Video *, IMG-2024*-WA*, Telegram, Signal."),
        ("Screen recordings", "Screen capture videos and meeting recordings: Screen Recording *, Recording *, OBS, Zoom, Meet."),
        ("Videos", "Films, clips and camera videos: .mp4 .mov .mkv .avi, VID_*, MOV_*."),
        ("Music", "Tracks and albums named with artist and title: .mp3 .flac .m4a."),
        ("Voice and podcasts", "Voice memos, call recordings, interviews and podcast episodes: .m4a .wav .amr, Recording_*, VN_*."),
        ("Wallpapers and artwork", "Wallpapers, posters and downloaded graphics: wallpaper, background, poster, 4k, hd, with no camera-style name."),
    ],
    "Study and research": [
        ("Lecture notes", "Class notes, slides and handouts: lecture, notes, chapter, week, module, handout."),
        ("Past papers", "Exam papers and practice questions: past paper, mock, exam, quiz, MCQ, marking scheme, answer key."),
        ("Textbooks", "Course books and reference books: textbook, edition, vol, .epub, large PDFs named after a book."),
        ("Assignments", "Coursework you write or submit: assignment, homework, essay, case study, project report, submission, draft."),
        ("Research papers", "Journal articles and papers: DOI-style names, author-year titles, arXiv, SSRN, journal, proceedings, thesis."),
        ("Standards and syllabi", "Official syllabi, curricula, standards and rule books: syllabus, scheme of study, IFRS, IAS, ISA, regulations."),
    ],
}

if __name__ == "__main__":
    for pack, rows in PACKS.items():
        names = [n.lower() for n, _ in rows]
        assert len(names) == len(set(names)), f"duplicate name in {pack}"
        assert all(d.strip() and "—" not in d for _, d in rows), pack
        assert all(not any(c in n for c in '\\/:*?"<>|') for n, _ in rows), pack
    print("presets OK")
