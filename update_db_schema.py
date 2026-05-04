import pandas as pd

file = 'treasury_master.xlsx'
all_sheets = pd.read_excel(file, sheet_name=None)
df = all_sheets['invoices']

# Add new columns if they don't exist
if 'product' not in df.columns:
    df['product'] = ""
if 'quantity' not in df.columns:
    df['quantity'] = 0
if 'note' not in df.columns:
    df['note'] = ""

all_sheets['invoices'] = df

with pd.ExcelWriter(file, engine='openpyxl') as writer:
    for sheet_name, sheet_df in all_sheets.items():
        sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

print("Database updated: Added 'product', 'quantity', and 'note' to invoices.")
