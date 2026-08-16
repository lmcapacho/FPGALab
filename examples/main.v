// Ejemplo de contrato compatible con examples/board_profile.json.
module top (
    input  wire       clk,
    input  wire       SW1,
    input  wire       SW2,
    input  wire [7:0] gpio_in,
    output wire       LED0, LED1, LED2, LED3, LED4, LED5, LED6, LED7,
    output wire [13:0] segments,
    output wire [7:0] gpio_out
);
    reg [26:0] counter = 0;
    always @(posedge clk)
        counter <= counter + 1'b1;

    // Rango visible: LED0 cambia a 11.44 Hz; cada LED siguiente a la mitad.
    assign {LED7, LED6, LED5, LED4, LED3, LED2, LED1, LED0} =
        counter[26:19] ^ {8{SW1}} ^ gpio_in;
    assign gpio_out = counter[15:8] ^ {8{SW2}};
    // Activo alto: abcdefg para cada dígito.
    assign segments = {7'b1110111, 7'b0111111}; // L y 0
endmodule
