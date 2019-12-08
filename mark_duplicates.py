import xlsxwriter
from collections import OrderedDict
from openpyxl import load_workbook

workbook = load_workbook("KuroNoKen_dump.xlsx")

for sheet in ('SCNs', 'BSDs'):
	worksheet = workbook.get_sheet_by_name(sheet)

	first_row = list(worksheet.rows)[0]
	header_values = [t.value for t in first_row]

	segs = {}

	for row in list(worksheet.rows)[1:]:
		jp = row[2].value
		if jp in segs:
			print(jp, "is a repeat of row", segs[jp])
			row[4].value = "=E%s" % segs[jp]
		else:
			# Set seg value to the first row it appears
			segs[jp] = row[2].row

workbook.save('KuroNoKen_dump.xlsx')