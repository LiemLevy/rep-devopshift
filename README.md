# AWS Infrastructure as Code Deployment Tool

## דרישות מקדימות

- Python 3.x
- Terraform מותקן ופעיל במערכת
- חשבון AWS עם הרשאות EC2, VPC, ELB
- AWS CLI מוגדר עם Credentials (הרצת `aws configure`)

## התקנת תלותים

הרץ:


## הרצת הסקריפט

בטרמינל, בתוך תיקיית הפרויקט, הרץ:


הסקריפט יבקש ממך:

- לבחור AMI (Ubuntu או Amazon Linux)
- לבחור סוג אינסטנס (t3.small או t3.medium)
- להזין אזור (רק us-east-1 נתמך)
- לבחור Availability Zone (us-east-1a או us-east-1b)
- להזין שם למאזן העומסים (ALB)

הוא ייצור את קובץ Terraform ויריץ את הפריסה, לאחר מכן יוודא שהמשאבים קיימים באמזון וייצור קובץ `aws_validation.json` עם פרטי השרת וה-ALB.

## ניקוי המשאבים

בכדי למחוק את התשתית שיצרת, הרץ בתיקיית `terraform`:


---

## הערות

- ודא ש-Terraform מותקן וניתן להריץ אותו מהטרמינל (`terraform version`).
- ודא שה-AWS CLI מוגדר עם הרשאות מתאימות.
- יש לך אפשרות לשדרג את הסקריפט ולהוסיף תמיכה במחיקה אוטומטית.

---
