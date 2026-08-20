export class UrusillaError extends Error {
  constructor(message, code = "urusilla_error") {
    super(message);
    this.name = new.target.name;
    this.code = code;
  }
}

export class ValidationError extends UrusillaError {
  constructor(message, code = "validation_error") {
    super(message, code);
  }
}

export class DecodeError extends UrusillaError {
  constructor(message, code = "decode_error") {
    super(message, code);
  }
}
