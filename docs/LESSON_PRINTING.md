# Two-sided lesson printing

Choose the book page range and 1, 2 or 4 pages per sheet in the lesson print wizard.
The app arranges those book pages into sheet sides before selecting fronts/backs.
Odd/even refers to the arranged sides, starting with the first selected page;
it does not filter individual odd/even book page numbers.

For manual two-sided printing:

1. Select **Fronts (odd sides)** and print.
2. Reload the same stack using the printer's usual manual-duplex direction.
3. Reopen the wizard, retain the same book pages and layout, and select
   **Backs (even sides)**. The last submitted settings are retained for this lesson.
4. Use **Reverse side order** if the printer needs the stack in the other order.
   It reverses complete sides, preserving each side's internal page order.

For example, pages 1–8 at two per sheet print fronts `[1, 2]`, `[5, 6]`
and backs `[3, 4]`, `[7, 8]`. Reversed backs print `[7, 8]`, `[3, 4]`.
With pages 1–5, the second back is blank and is retained even when reversing;
otherwise the printed backs would shift onto the wrong fronts. Partly filled
sides also retain their blank cells.

In the browser/printer dialog use **all pages**, **one-sided printing** and
**one page per sheet** for each manual pass. Match the wizard's paper size and
orientation, and disable headers/footers. The wizard has already selected and
arranged the sides; applying another odd/even or multiple-page filter there
would filter them a second time.

For automatic duplex printing, select **All sides** in the wizard and enable
two-sided printing in the printer dialog. Feed direction and any reverse-order
requirement depend on the physical printer; the preview lists each side's pages
before the system print dialog opens.
