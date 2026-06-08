from __future__ import annotations

DEPARTMENTS = [
    ("Engineering", "Build and maintain software platforms"),
    ("Data", "Data engineering, analytics and AI"),
    ("Marketing", "Demand generation and brand"),
    ("Finance", "Financial planning and accounting"),
    ("HR", "People operations and talent"),
    ("Operations", "Business operations and support"),
    ("Product", "Product management and strategy"),
    ("Sales", "Revenue and account management"),
]

OFFICES = [
    ("Paris HQ", "France", "Paris", "Europe/Paris", 850),
    ("Berlin Hub", "Germany", "Berlin", "Europe/Berlin", 500),
    ("London Office", "United Kingdom", "London", "Europe/London", 600),
    ("Madrid Office", "Spain", "Madrid", "Europe/Madrid", 350),
    ("New York Office", "United States", "New York", "America/New_York", 700),
    ("Toronto Office", "Canada", "Toronto", "America/Toronto", 400),
    ("São Paulo Office", "Brazil", "Sao Paulo", "America/Sao_Paulo", 300),
    ("Singapore Office", "Singapore", "Singapore", "Asia/Singapore", 450),
    ("Bangalore Office", "India", "Bangalore", "Asia/Kolkata", 750),
    ("Tokyo Office", "Japan", "Tokyo", "Asia/Tokyo", 500),
]

POSITIONS = [
    ("Data Engineer", "Data", "Junior", 45000, 70000),
    ("Data Engineer", "Data", "Mid", 70000, 100000),
    ("Data Engineer", "Data", "Senior", 100000, 140000),
    ("Data Scientist", "Data", "Mid", 75000, 110000),
    ("Data Scientist", "Data", "Senior", 110000, 150000),
    ("DevOps Engineer", "Engineering", "Mid", 80000, 115000),
    ("DevOps Engineer", "Engineering", "Senior", 115000, 155000),
    ("Software Engineer", "Engineering", "Junior", 50000, 80000),
    ("Software Engineer", "Engineering", "Mid", 80000, 120000),
    ("Software Engineer", "Engineering", "Senior", 120000, 165000),
    ("Product Manager", "Product", "Mid", 85000, 125000),
    ("Product Manager", "Product", "Senior", 125000, 170000),
    ("HR Business Partner", "HR", "Mid", 60000, 90000),
    ("HR Business Partner", "HR", "Senior", 90000, 120000),
    ("Financial Analyst", "Finance", "Junior", 50000, 78000),
    ("Financial Analyst", "Finance", "Mid", 78000, 105000),
    ("Sales Executive", "Sales", "Junior", 45000, 80000),
    ("Sales Executive", "Sales", "Mid", 80000, 125000),
    ("Operations Manager", "Operations", "Senior", 95000, 135000),
    ("Director", "General", "Director", 150000, 240000),
]

LEVEL_WEIGHTS = {
    "Junior": 0.46,
    "Mid": 0.30,
    "Senior": 0.17,
    "Lead": 0.05,
    "Director": 0.02,
}

COUNTRY_SALARY_MULTIPLIER = {
    "France": 1.0,
    "Germany": 1.07,
    "United Kingdom": 1.12,
    "Spain": 0.88,
    "United States": 1.30,
    "Canada": 1.12,
    "Brazil": 0.62,
    "Singapore": 1.23,
    "India": 0.55,
    "Japan": 1.15,
}

DEPARTMENT_TURNOVER = {
    "Engineering": 0.06,
    "Data": 0.08,
    "Marketing": 0.14,
    "Finance": 0.09,
    "HR": 0.1,
    "Operations": 0.12,
    "Product": 0.07,
    "Sales": 0.18,
}
